import json
import logging
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

from botocore.exceptions import ClientError
from django.core.cache import cache
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View
from geopy.geocoders import Nominatim
from urllib.parse import unquote
from django.utils.translation import gettext_lazy as _

# Assuming your Collection model is here. Adjust if necessary.
from lacos.blam.models import Bundle, Collection
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
)
from django.core.paginator import Paginator

from lacos.explorer.permissions import ACLPermissionMixin
from lacos.explorer.search import search_archives
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.file_discovery_service import FileDiscoveryService

# Get an instance of a logger
logger = logging.getLogger(__name__)

BUNDLES_PER_PAGE = 10


def _bundle_queryset_for_collection(collection):
    return (
        BundleStructuralInfo.objects.filter(is_member_of_collection=collection)
        .select_related("bundle", "is_member_of_collection")
        .prefetch_related(
            "bundle_topics",
            "additional_metadata_files",
            Prefetch(
                "bundle__resources",
                queryset=BundleResources.objects.prefetch_related(
                    "bundle_media_resources",
                    "bundle_written_resources",
                    "bundle_other_resources",
                ),
            ),
            "bundle__general_info",
            "bundle__general_info__object_languages",
        )
        .order_by("bundle__identifier")
    )


def _build_bundle_context(struct_info):
    bundle = struct_info.bundle
    bundle_resources = list(bundle.resources.all())
    primary_resources = bundle_resources[0] if bundle_resources else None

    if primary_resources:
        media_resources = list(primary_resources.bundle_media_resources.all())
        written_resources = list(primary_resources.bundle_written_resources.all())
        other_resources = list(primary_resources.bundle_other_resources.all())
    else:
        media_resources = []
        written_resources = []
        other_resources = []

    media_like_other = []
    for res in other_resources:
        mime = getattr(res, 'mime_type', '') or ''
        lowered = mime.lower()
        if lowered.startswith('video/') or lowered.startswith('audio/'):
            media_like_other.append(res)
    if media_like_other:
        media_resources.extend(media_like_other)
        other_resources = [res for res in other_resources if res not in media_like_other]

    metadata_files = list(struct_info.additional_metadata_files.all())
    topics = list(struct_info.bundle_topics.all())

    return {
        "structural_info": struct_info,
        "bundle": bundle,
        "primary_resources": primary_resources,
        "media_resources": media_resources,
        "written_resources": written_resources,
        "other_resources": other_resources,
        "metadata_files": metadata_files,
        "topics": topics,
    }


def _paginate_bundle_contexts(collection, page_number, per_page=BUNDLES_PER_PAGE):
    queryset = _bundle_queryset_for_collection(collection)
    paginator = Paginator(queryset, per_page)

    if paginator.count == 0:
        return None, []

    page_obj = paginator.get_page(page_number)
    contexts = [_build_bundle_context(struct_info) for struct_info in page_obj.object_list]
    return page_obj, contexts


def resolve_existing_object(
    resource_service,
    object_locations: Sequence[Tuple[Optional[str], Optional[str]]],
) -> Tuple[Optional[str], Optional[str]]:
    """Return the first (bucket, key) pair that exists in storage."""
    seen: set[Tuple[str, str]] = set()

    for bucket, key in object_locations:
        if not bucket or not key:
            continue

        identifier = (bucket, key)
        if identifier in seen:
            continue
        seen.add(identifier)

        try:
            resource_service.s3_client.head_object(Bucket=bucket, Key=key)
            return bucket, key
        except ClientError as error:
            error_code = error.response.get('Error', {}).get('Code')
            if error_code in {'404', 'NoSuchKey', 'NotFound'}:
                continue
            raise

    return None, None


def _iter_bundle_resources(bundle) -> Iterable:
    """Yield all resources associated with the bundle."""
    resources_container = bundle.resources.first()
    if resources_container:
        yield from resources_container.bundle_media_resources.all()
        yield from resources_container.bundle_written_resources.all()
        yield from resources_container.bundle_other_resources.all()

    struct_info = bundle.structural_info.first()
    if struct_info:
        yield from struct_info.additional_metadata_files.all()


def _resolve_resource_to_presigned(
    resource_service,
    resource,
    bundle,
    collection_for_path,
):
    """Resolve a resource to its storage location and presigned URL."""

    fallback_bucket = (
        getattr(bundle, "import_bucket", None)
        or (
            getattr(collection_for_path, "import_bucket", None)
            if collection_for_path
            else None
        )
    ) or resource_service.production_bucket

    candidate_locations: list[tuple[Optional[str], Optional[str]]] = []

    location = resource_service.resolve_pid_to_s3(getattr(resource, "file_pid", None))
    if location:
        candidate_locations.append((location.s3_bucket, location.s3_key))
        candidate_locations.append((fallback_bucket, location.s3_key))

    def add_import_location(import_bucket: Optional[str], import_key: Optional[str]):
        if not import_bucket or not import_key:
            return
        base_path = PurePosixPath(import_key).parent
        candidate_locations.append(
            (import_bucket, str(base_path / "Resources" / resource.file_name))
        )

    add_import_location(
        getattr(bundle, "import_bucket", None),
        getattr(bundle, "import_object_key", None),
    )
    if collection_for_path:
        add_import_location(
            getattr(collection_for_path, "import_bucket", None),
            getattr(collection_for_path, "import_object_key", None),
        )

    discovery_service = FileDiscoveryService()
    derived_key = None
    if collection_for_path:
        try:
            derived_key = discovery_service.form_resource_path(
                collection_for_path.id,
                bundle.id,
                resource.file_name,
            )
        except Exception:  # pragma: no cover - defensive fallback
            derived_key = None

    if derived_key:
        candidate_locations.append((fallback_bucket, derived_key))
        if fallback_bucket != resource_service.production_bucket:
            candidate_locations.append(
                (resource_service.production_bucket, derived_key)
            )

    bucket_name, object_key = resolve_existing_object(
        resource_service, candidate_locations
    )

    if not bucket_name or not object_key:
        return None

    presigned_url = resource_service.generate_presigned_url(
        bucket_name,
        object_key,
    )

    return {
        "bucket": bucket_name,
        "key": object_key,
        "url": presigned_url,
    }


def _parse_elan_document(resource_service, bucket_name: str, object_key: str) -> dict:
    """Fetch and parse ELAN (.eaf) metadata for annotations and media links."""
    try:
        response = resource_service.s3_client.get_object(
            Bucket=bucket_name,
            Key=object_key,
        )
    except ClientError as exc:  # pragma: no cover - depends on storage backend
        logger.error(
            "Unable to fetch ELAN document %s from bucket %s: %s",
            object_key,
            bucket_name,
            exc,
        )
        return {"annotations": [], "media_files": []}

    raw_bytes = response.get("Body").read()
    try:
        elan_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        elan_text = raw_bytes.decode("utf-8", errors="replace")

    return _parse_elan_text(elan_text)


def _parse_elan_text(elan_text: str) -> dict:
    try:
        root = ET.fromstring(elan_text)
    except ET.ParseError as exc:
        logger.error("Failed to parse ELAN document: %s", exc)
        return {"annotations": [], "media_files": []}

    timeslots: dict[str, Optional[int]] = {}
    for slot in root.findall("./TIME_ORDER/TIME_SLOT"):
        slot_id = slot.attrib.get("TIME_SLOT_ID")
        if not slot_id:
            continue
        time_value = slot.attrib.get("TIME_VALUE")
        try:
            timeslots[slot_id] = int(time_value) if time_value is not None else None
        except ValueError:
            timeslots[slot_id] = None

    media_files: list[str] = []
    for descriptor in root.findall("./HEADER/MEDIA_DESCRIPTOR"):
        relative = descriptor.attrib.get("RELATIVE_MEDIA_URL")
        media_url = relative or descriptor.attrib.get("MEDIA_URL")
        if media_url:
            media_files.append(media_url.strip())

    tier_headers: set[str] = set()
    annotations_map: dict[str, dict[str, Optional[float]]] = {}

    def ensure_entry(annotation_id: str) -> dict:
        entry = annotations_map.get(annotation_id)
        if entry is None:
            entry = {
                "id": annotation_id,
                "start": None,
                "end": None,
                "tiers": {},
            }
            annotations_map[annotation_id] = entry
        return entry

    def _time_to_seconds(value: Optional[int]) -> Optional[float]:
        if value is None:
            return None
        return (value or 0) / 1000

    for tier in root.findall("TIER"):
        tier_id = tier.attrib.get("TIER_ID", "Tier")
        tier_headers.add(tier_id)

        for annotation in tier.findall("./ANNOTATION"):
            alignable = annotation.find("ALIGNABLE_ANNOTATION")
            ref_annotation = annotation.find("REF_ANNOTATION")

            if alignable is not None:
                annotation_id = alignable.attrib.get("ANNOTATION_ID")
                if not annotation_id:
                    continue

                entry = ensure_entry(annotation_id)

                start_ref = alignable.attrib.get("TIME_SLOT_REF1")
                end_ref = alignable.attrib.get("TIME_SLOT_REF2")
                entry["start"] = _time_to_seconds(timeslots.get(start_ref))
                entry["end"] = _time_to_seconds(timeslots.get(end_ref))

                value_element = alignable.find("ANNOTATION_VALUE")
                value_text = (
                    value_element.text.strip()
                    if value_element is not None and value_element.text
                    else ""
                )

                if value_text:
                    entry.setdefault("tiers", {})[tier_id] = value_text

            elif ref_annotation is not None:
                reference_id = ref_annotation.attrib.get("ANNOTATION_REF")
                if not reference_id:
                    continue

                entry = ensure_entry(reference_id)

                value_element = ref_annotation.find("ANNOTATION_VALUE")
                value_text = (
                    value_element.text.strip()
                    if value_element is not None and value_element.text
                    else ""
                )

                if value_text:
                    entry.setdefault("tiers", {})[tier_id] = value_text

    annotations = list(annotations_map.values())

    if "Tier" in tier_headers and len(tier_headers) > 1:
        tier_headers.discard("Tier")

    tier_list = sorted(tier_headers)

    for entry in annotations:
        entry['ordered_tiers'] = [
            {
                'name': tier,
                'value': entry.get('tiers', {}).get(tier, ''),
            }
            for tier in tier_list
        ]

    annotations.sort(
        key=lambda item: (
            item["start"] if item["start"] is not None else -1,
            item.get("id", ""),
        )
    )

    for entry in annotations:
        tier_texts = [text for text in entry.get("tiers", {}).values() if text]
        entry["value"] = tier_texts[0] if tier_texts else ""

    return {
        "annotations": annotations,
        "media_files": media_files,
        "tier_headers": tier_list,
    }


def _pick_elan_audio_resource(bundle, target_resource, elan_data: dict):
    """Choose the most relevant audio resource for an ELAN file."""

    base_names = {Path(target_resource.file_name).stem.lower()}
    for candidate in elan_data.get("media_files", []):
        if not candidate:
            continue
        candidate_name = Path(unquote(candidate)).name
        base_names.add(Path(candidate_name).stem.lower())

    audio_candidates: list[tuple[int, object]] = []

    for resource in _iter_bundle_resources(bundle):
        if resource.id == target_resource.id:
            continue
        mime = getattr(resource, "mime_type", "") or ""
        lowered_mime = mime.lower()
        if not lowered_mime.startswith("audio/"):
            continue

        resource_stem = Path(resource.file_name).stem.lower()
        score = 0
        if resource_stem in base_names:
            score += 2
        if resource_stem == Path(target_resource.file_name).stem.lower():
            score += 1

        # Allow generic fallback when we have no confident match yet
        if score == 0 and not audio_candidates:
            score = 1

        audio_candidates.append((score, resource))

    if not audio_candidates:
        return None

    audio_candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_resource = audio_candidates[0]
    return best_resource if best_score > 0 else None


def find_resource_in_bundle(
    bundle,
    *,
    resource_id: Optional[str] = None,
    file_pid: Optional[str] = None,
):
    """Locate a resource within a bundle by id or PID."""
    if resource_id is None and file_pid is None:
        return None

    for resource in _iter_bundle_resources(bundle):
        if resource_id is not None and str(resource.id) == str(resource_id):
            return resource
        if file_pid is not None and getattr(resource, 'file_pid', None) == file_pid:
            return resource

    return None


def get_formatted_location(location):
    """
    Get formatted location string from location object.
    Falls back to different fields in order of preference.
    """
    if location:
        if location.location_name:
            return location.location_name
        elif location.region_name:
            return location.region_name
        elif location.country_name:
            return location.country_name
        elif location.geo_location:
            # If we only have coordinates, try to get location name from reverse geocoding
            return get_location_from_coordinates(location.geo_location)
    return ""


# Cache results to avoid repeated API calls
@lru_cache(maxsize=128)
def get_location_from_coordinates(coordinates):
    """
    Get location name from coordinates using Nominatim (OpenStreetMap).
    Coordinates should be in format "LATITUDE,LONGITUDE" like "50.926735,6.930392"
    """
    try:
        # Create a safe cache key by removing spaces and non-alphanumeric characters
        safe_coordinates = re.sub(r'[^\w\-]', '_', coordinates)
        cache_key = f"geo_location_{safe_coordinates}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        if not coordinates or ',' not in coordinates:
            return coordinates
            
        lat, lng = coordinates.split(',')
        lat = lat.strip()
        lng = lng.strip()
        
        # Just return the coordinates for now to avoid API calls
        # This prevents rate limiting while you're developing
        formatted_coords = f"{lat}, {lng}"
        
        # Store in cache for future use
        cache.set(cache_key, formatted_coords, timeout=60*60*24*30)  # Cache for 30 days
        
        return formatted_coords
        
        # DISABLED GEOCODING TO PREVENT RATE LIMITING
        # Uncomment below for production use
        
        # # Initialize the geocoder with a longer timeout
        # geolocator = Nominatim(user_agent="lacos_app", timeout=10)
        
        # # Reverse geocode
        # location = geolocator.reverse((lat, lng), language='en')
        
        # if location and location.address:
        #     # Get a shorter version of the address if possible
        #     address_parts = location.raw.get('address', {})
        #     if 'city' in address_parts and 'country' in address_parts:
        #         result = f"{address_parts['city']}, {address_parts['country']}"
        #     elif 'town' in address_parts and 'country' in address_parts:
        #         result = f"{address_parts['town']}, {address_parts['country']}"
        #     elif 'village' in address_parts and 'country' in address_parts:
        #         result = f"{address_parts['village']}, {address_parts['country']}"
        #     else:
        #         # Fall back to the full address (might be long)
        #         result = location.address
                
        #     # Store in cache for future use
        #     cache.set(cache_key, result, timeout=60*60*24*30)  # Cache for 30 days
        #     return result
        
        # return coordinates
    except Exception as e:
        logger.error(f"Error fetching location from coordinates: {e}")
        return coordinates


class CollectionListView(ListView):
    model = Collection
    # The template name is deduced by default as: 'blam/collection_list.html'
    # Since our template is directly under 'lacos/lacos/explorer/templates/',
    # we specify the template name explicitly.
    template_name = "collection_list.html"
    context_object_name = "collection_list"  # To match the template variable

    def get_queryset(self):
        """Explicitly return all collections and log the count."""
        logger.info("Fetching collections in CollectionListView...")
        queryset = Collection.objects.all()
        collection_count = queryset.count()
        logger.info(f"Found {collection_count} collections.")
        return queryset
        
    def get_context_data(self, **kwargs):
        """Add processed location data to the context."""
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        context["search_query"] = search_query
        if search_query:
            search_results = search_archives(search_query)
            context["search_results"] = search_results
            context["collection_search_results"] = [
                result for result in search_results if result.kind == "collection"
            ]
            context["bundle_search_results"] = [
                result for result in search_results if result.kind == "bundle"
            ]
        # Process locations for each collection
        collections_with_locations = []
        for collection in context['collection_list']:
            if collection.get_general_info and collection.get_general_info.location:
                location = collection.get_general_info.location
                collection.formatted_location = get_formatted_location(location)
            else:
                collection.formatted_location = ""
            collections_with_locations.append(collection)
        
        context['collection_list'] = collections_with_locations
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('HX-Request') and 'q' in self.request.GET:
            return render(
                self.request,
                'explorer/partials/collection_search_results_content.html',
                context,
            )
        return super().render_to_response(context, **response_kwargs)


class CollectionDetailView(DetailView):
    model = Collection
    # The template name is deduced by default as: 'blam/collection_detail.html'
    # Since our template is directly under 'lacos/lacos/explorer/templates/',
    # we specify the template name explicitly.
    template_name = "collection_detail.html"
    context_object_name = "collection"  # To match the template variable

    def get_queryset(self):
        return Collection.objects.prefetch_related(
            "general_info",
            "general_info__object_languages",
            "publication_info",
            "publication_info__creators",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add formatted location to the collection
        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
        else:
            self.object.formatted_location = ""
            
        page_number = self.request.GET.get('bundle_page')
        page_obj, bundle_contexts = _paginate_bundle_contexts(self.object, page_number)

        query_params = self.request.GET.copy()
        if 'bundle_page' in query_params:
            query_params.pop('bundle_page')
        base_query = query_params.urlencode()
        if base_query:
            base_url = f"{self.request.path}?{base_query}"
        else:
            base_url = self.request.path
        separator = '&' if '?' in base_url else '?'

        context['bundle_page_obj'] = page_obj
        context['bundle_contexts'] = bundle_contexts
        context['bundle_page_base_url'] = base_url
        context['bundle_page_separator'] = separator
        context['bundles_total'] = page_obj.paginator.count if page_obj else 0

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('HX-Request') and 'bundle_page' in self.request.GET:
            return render(
                self.request,
                'explorer/partials/collection_bundles_table.html',
                context,
            )
        return super().render_to_response(context, **response_kwargs)


class BundleDetailView(ACLPermissionMixin, DetailView):
    model = Bundle
    template_name = "bundle_detail.html"
    context_object_name = "bundle"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = getattr(self, "acl_result", None)
        context["acl_check_result"] = result
        context["can_read_bundle"] = True if result is None else result.allowed
        context["acl_enforcement_enabled"] = (
            self.get_acl_service().enforcement_enabled  # type: ignore[attr-defined]
        )
        
        # Get the collection this bundle belongs to
        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            context['collection'] = self.object.structural_info.first().is_member_of_collection
        
        # Add formatted location
        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
        else:
            self.object.formatted_location = ""
            
        # Get all resources
        context['media_resources'] = []
        context['written_resources'] = []
        context['other_resources'] = []
        context['metadata_files'] = []
        
        if self.object.resources.first():
            resources = self.object.resources.first()
            context['media_resources'] = resources.bundle_media_resources.all()
            context['written_resources'] = resources.bundle_written_resources.all()
            context['other_resources'] = resources.bundle_other_resources.all()
            
        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            context['metadata_files'] = self.object.structural_info.first().additional_metadata_files.all()
            
        return context


class BundleResourcesView(View):
    """View for accessing bundle resources directly or listing them"""
    permission_denied_message = _("You do not have permission to access this bundle.")
    
    def get(self, request, pk, resource_id=None):
        bundle = get_object_or_404(Bundle, pk=pk)
        acl_service = ACLEvaluationService()
        acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")
        if acl_service.enforcement_enabled and not acl_result.allowed:
            return HttpResponseForbidden(self.permission_denied_message)

        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection
        
        # If a specific resource is requested, try to serve it directly
        if resource_id:
            try:
                # URL decode the resource_id since it may contain special characters
                decoded_resource_id = unquote(resource_id)
                
                # Remove the 'ID_' prefix if it exists
                if decoded_resource_id.startswith('ID_'):
                    decoded_resource_id = decoded_resource_id[3:]
                
                from lacos.storage.services.file_discovery_service import FileDiscoveryService
                from lacos.storage.services.resource_mapping_service import ResourceMappingService

                resource_service = ResourceMappingService()
                location = resource_service.resolve_pid_to_s3(decoded_resource_id)
                if not location:
                    raise ValueError(f"No S3 location found for PID: {decoded_resource_id}")

                resource_obj = find_resource_in_bundle(bundle, file_pid=decoded_resource_id)

                fallback_bucket = (
                    getattr(bundle, 'import_bucket', None)
                    or (
                        getattr(collection_for_path, 'import_bucket', None)
                        if collection_for_path
                        else None
                    )
                    or resource_service.production_bucket
                )

                candidate_locations: list[tuple[Optional[str], Optional[str]]] = []
                candidate_locations.append((location.s3_bucket, location.s3_key))
                if fallback_bucket:
                    candidate_locations.append((fallback_bucket, location.s3_key))

                def add_import_location(import_bucket: Optional[str], import_key: Optional[str]):
                    if not resource_obj or not import_bucket or not import_key:
                        return
                    base_path = PurePosixPath(import_key).parent
                    candidate_locations.append(
                        (import_bucket, str(base_path / 'Resources' / resource_obj.file_name))
                    )

                add_import_location(getattr(bundle, 'import_bucket', None), getattr(bundle, 'import_object_key', None))
                if collection_for_path:
                    add_import_location(
                        getattr(collection_for_path, 'import_bucket', None),
                        getattr(collection_for_path, 'import_object_key', None),
                    )

                if resource_obj and collection_for_path:
                    try:
                        discovery_service = FileDiscoveryService()
                        derived_key = discovery_service.form_resource_path(
                            collection_for_path.id,
                            bundle.id,
                            resource_obj.file_name,
                        )
                    except Exception:  # pragma: no cover - defensive
                        derived_key = None

                    if derived_key:
                        candidate_locations.append((fallback_bucket, derived_key))
                        if fallback_bucket != resource_service.production_bucket:
                            candidate_locations.append((resource_service.production_bucket, derived_key))

                resolved_bucket, resolved_key = resolve_existing_object(resource_service, candidate_locations)

                if not resolved_bucket or not resolved_key:
                    raise ValueError("Resource key not available in candidate locations")

                presigned_url = resource_service.generate_presigned_url(
                    resolved_bucket,
                    resolved_key,
                )

                return redirect(presigned_url)
                
            except ValueError as e:
                logger.error(f"Resource mapping service error: {e}")
                raise Http404(f"Resource {resource_id} not found or cannot be accessed")
            except Exception as e:
                logger.error(f"Error accessing resource: {e}")
                return HttpResponse(f"Error accessing resource: {str(e)}", status=500)
        
        # If no specific resource is requested, show the resources list view
        context = {
            'bundle': bundle,
            'media_resources': [],
            'written_resources': [],
            'other_resources': [],
            'metadata_files': [],
            'restricted_resources': False,
        }
        context['acl_check_result'] = acl_result
        context['can_read_bundle'] = acl_result.allowed
        context['acl_enforcement_enabled'] = acl_service.enforcement_enabled
        
        resources = bundle.resources.first()
        if acl_result.allowed and resources:
            context['media_resources'] = resources.bundle_media_resources.all()
            context['written_resources'] = resources.bundle_written_resources.all()
            context['other_resources'] = resources.bundle_other_resources.all()
        elif resources:
            context['restricted_resources'] = True

        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            context['collection'] = bundle.structural_info.first().is_member_of_collection
            context['metadata_files'] = bundle.structural_info.first().additional_metadata_files.all()
            if not acl_result.allowed:
                context['metadata_files'] = []
        
        return render(request, 'bundle_resources.html', context)


class ResourceAccessView(View):
    """View for accessing resources either through direct download or streaming"""
    permission_denied_message = _("You do not have permission to access this resource.")
    
    def get(self, request, bundle_id, resource_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        acl_service = ACLEvaluationService()
        acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")
        if acl_service.enforcement_enabled and not acl_result.allowed:
            return HttpResponseForbidden(self.permission_denied_message)

        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection
        action = request.GET.get('action', 'download')  # Default to download if no action specified
        
        try:
            # Find the resource by its ID (UUID) first
            resource = find_resource_in_bundle(bundle, resource_id=resource_id)

            if not resource:
                raise Http404(f"Resource with id {resource_id} not found in bundle {bundle_id}")

            # Get the PID from the resource
            mime_type = getattr(resource, 'mime_type', None)
            normalized_mime_type = mime_type.lower().strip() if mime_type else ''
            extension = (
                Path(getattr(resource, 'file_name', '')).suffix.lower().lstrip('.')
                if getattr(resource, 'file_name', None)
                else ''
            )
            is_elan = extension in {'eaf', 'elan'} or normalized_mime_type == 'text/x-eaf+xml'

            from lacos.storage.services.resource_mapping_service import ResourceMappingService

            resource_service = ResourceMappingService()

            storage_resolution = _resolve_resource_to_presigned(
                resource_service,
                resource,
                bundle,
                collection_for_path,
            )

            if not storage_resolution:
                raise ValueError("Unable to determine S3 location for resource")

            bucket_name = storage_resolution['bucket']
            object_key = storage_resolution['key']
            presigned_url = storage_resolution['url']

            elan_context = None
            if is_elan:
                elan_data = _parse_elan_document(
                    resource_service,
                    bucket_name,
                    object_key,
                )

                audio_resource = _pick_elan_audio_resource(
                    bundle,
                    resource,
                    elan_data,
                )

                audio_url = None
                audio_file_name = None
                if audio_resource:
                    audio_resolution = _resolve_resource_to_presigned(
                        resource_service,
                        audio_resource,
                        bundle,
                        collection_for_path,
                    )
                    if audio_resolution:
                        audio_url = audio_resolution['url']
                        audio_file_name = getattr(audio_resource, 'file_name', '')

                elan_context = {
                    'annotations': elan_data.get('annotations', []),
                    'media_files': elan_data.get('media_files', []),
                    'audio_url': audio_url,
                    'audio_file_name': audio_file_name,
                    'tier_headers': elan_data.get('tier_headers', []),
                }

            is_htmx = request.headers.get('HX-Request') == 'true'

            if is_htmx and action in {'play', 'view'}:
                media_type = None
                if normalized_mime_type.startswith('audio/'):
                    media_type = 'audio'
                elif normalized_mime_type.startswith('video/'):
                    media_type = 'video'
                elif normalized_mime_type.startswith('image/'):
                    media_type = 'image'
                elif normalized_mime_type == 'application/pdf':
                    media_type = 'pdf'
                elif is_elan:
                    media_type = 'elan'

                modal_context = {
                    'resource_name': resource.file_name,
                    'resource_description': getattr(resource, 'file_description', ''),
                    'mime_type': mime_type,
                    'media_type': media_type,
                    'stream_url': presigned_url if media_type in {'audio', 'video'} else None,
                    'preview_url': presigned_url,
                    'download_url': presigned_url,
                    'elan_context': elan_context,
                }

                response = render(
                    request,
                    'explorer/partials/resource_modal_content.html',
                    modal_context,
                )
                response['HX-Trigger'] = json.dumps({'showResourceModal': True})
                return response

            # For direct download, just redirect to the presigned URL
            if action == 'download':
                return redirect(presigned_url)

            # For streaming/viewing, handle based on the mime type
            if normalized_mime_type.startswith('audio/') or normalized_mime_type.startswith('video/'):
                if action == 'play':
                    return render(
                        request,
                        'resource_player.html',
                        {
                            'resource_name': resource.file_name,
                            'mime_type': mime_type,
                            'stream_url': presigned_url,
                            'download_url': presigned_url,
                        },
                    )

                return redirect(presigned_url)
            
            elif normalized_mime_type.startswith('image/') or normalized_mime_type == 'application/pdf':
                # For images and PDFs, redirect to view in browser
                return redirect(presigned_url)
            else:
                # For other file types, default to download
                return redirect(presigned_url)
                
        except ValueError as e:
            logger.error(f"Resource mapping service error: {e}")
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error(f"Error accessing resource: {e}")
            return HttpResponse(f"Error accessing resource: {str(e)}", status=500) 
