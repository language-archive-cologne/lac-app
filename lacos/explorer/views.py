import json
import logging
import re
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Iterable, Optional, Sequence, Tuple

from botocore.exceptions import ClientError
from django.core.cache import cache
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View
from geopy.geocoders import Nominatim
from urllib.parse import unquote

# Assuming your Collection model is here. Adjust if necessary.
from lacos.blam.models import Collection, Bundle

# Get an instance of a logger
logger = logging.getLogger(__name__)


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


class CollectionDetailView(DetailView):
    model = Collection
    # The template name is deduced by default as: 'blam/collection_detail.html'
    # Since our template is directly under 'lacos/lacos/explorer/templates/',
    # we specify the template name explicitly.
    template_name = "collection_detail.html"
    context_object_name = "collection"  # To match the template variable

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add formatted location to the collection
        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
        else:
            self.object.formatted_location = ""
            
        # Get all resources from bundles in this collection
        context['collection_media_resources'] = []
        context['collection_written_resources'] = []
        context['collection_other_resources'] = []
        context['collection_metadata_files'] = []
        
        # Get bundles in this collection
        bundles = Bundle.objects.filter(structural_info__is_member_of_collection=self.object)
        
        # Collect resources from all bundles
        for bundle in bundles:
            if bundle.resources.first():
                resources = bundle.resources.first()
                context['collection_media_resources'].extend(resources.bundle_media_resources.all())
                context['collection_written_resources'].extend(resources.bundle_written_resources.all())
                context['collection_other_resources'].extend(resources.bundle_other_resources.all())
                
            if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
                context['collection_metadata_files'].extend(bundle.structural_info.first().additional_metadata_files.all())
                
        return context


class BundleDetailView(DetailView):
    model = Bundle
    template_name = "bundle_detail.html"
    context_object_name = "bundle"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
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
    
    def get(self, request, pk, resource_id=None):
        bundle = get_object_or_404(Bundle, pk=pk)
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
            'metadata_files': []
        }
        
        if bundle.resources.first():
            resources = bundle.resources.first()
            context['media_resources'] = resources.bundle_media_resources.all()
            context['written_resources'] = resources.bundle_written_resources.all()
            context['other_resources'] = resources.bundle_other_resources.all()
            
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            context['collection'] = bundle.structural_info.first().is_member_of_collection
            context['metadata_files'] = bundle.structural_info.first().additional_metadata_files.all()
        
        return render(request, 'bundle_resources.html', context)


class ResourceAccessView(View):
    """View for accessing resources either through direct download or streaming"""
    
    def get(self, request, bundle_id, resource_id):
        bundle = get_object_or_404(Bundle, pk=bundle_id)
        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection
        action = request.GET.get('action', 'download')  # Default to download if no action specified
        
        try:
            # Find the resource by its ID (UUID) first
            from django.contrib.contenttypes.models import ContentType
            from lacos.storage.models.s3_resource_location import S3ResourceLocation
            
            # Get the resource
            resource = find_resource_in_bundle(bundle, resource_id=resource_id)

            if not resource:
                raise Http404(f"Resource with id {resource_id} not found in bundle {bundle_id}")

            # Get the PID from the resource
            resource_pid = resource.file_pid
            mime_type = getattr(resource, 'mime_type', None)

            from lacos.storage.services.resource_mapping_service import ResourceMappingService
            from lacos.storage.services.file_discovery_service import FileDiscoveryService

            resource_service = ResourceMappingService()

            location = resource_service.resolve_pid_to_s3(resource_pid)
            fallback_bucket = (
                getattr(bundle, 'import_bucket', None)
                or (
                    getattr(collection_for_path, 'import_bucket', None)
                    if collection_for_path
                    else None
                )
            ) or resource_service.production_bucket

            candidate_locations: list[tuple[Optional[str], Optional[str]]] = []

            if location:
                candidate_locations.append((location.s3_bucket, location.s3_key))
                candidate_locations.append((fallback_bucket, location.s3_key))

            def add_import_location(import_bucket: Optional[str], import_key: Optional[str]):
                if not import_bucket or not import_key:
                    return
                base_path = PurePosixPath(import_key).parent
                candidate_locations.append(
                    (import_bucket, str(base_path / 'Resources' / resource.file_name))
                )

            add_import_location(getattr(bundle, 'import_bucket', None), getattr(bundle, 'import_object_key', None))
            if collection_for_path:
                add_import_location(
                    getattr(collection_for_path, 'import_bucket', None),
                    getattr(collection_for_path, 'import_object_key', None),
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
                except Exception:  # pragma: no cover - defensive
                    derived_key = None

            if derived_key:
                candidate_locations.append((fallback_bucket, derived_key))
                if fallback_bucket != resource_service.production_bucket:
                    candidate_locations.append((resource_service.production_bucket, derived_key))

            bucket_name, object_key = resolve_existing_object(resource_service, candidate_locations)

            if not bucket_name or not object_key:
                raise ValueError("Unable to determine S3 location for resource")

            presigned_url = resource_service.generate_presigned_url(bucket_name, object_key)

            is_htmx = request.headers.get('HX-Request') == 'true'

            if is_htmx and action in {'play', 'view'}:
                media_type = None
                if mime_type and mime_type.startswith('audio/'):
                    media_type = 'audio'
                elif mime_type and mime_type.startswith('video/'):
                    media_type = 'video'
                elif mime_type and mime_type.startswith('image/'):
                    media_type = 'image'
                elif mime_type == 'application/pdf':
                    media_type = 'pdf'

                modal_context = {
                    'resource_name': resource.file_name,
                    'resource_description': getattr(resource, 'file_description', ''),
                    'mime_type': mime_type,
                    'media_type': media_type,
                    'stream_url': presigned_url if media_type in {'audio', 'video'} else None,
                    'preview_url': presigned_url,
                    'download_url': presigned_url,
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
            if mime_type and (mime_type.startswith('audio/') or mime_type.startswith('video/')):
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
            
            elif mime_type and (mime_type.startswith('image/') or mime_type == 'application/pdf'):
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
