"""Bundle views for the explorer app."""

import json
import logging
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import unquote

from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView

from lacos.blam.models import Bundle
from lacos.blam.mappers.bundle.write.bundle_exporter import BundleExporter
from lacos.blam.serializers import BundleJsonLdSerializer
from lacos.explorer.media_utils import determine_media_type, guess_source_mime_type
from lacos.explorer.permissions import ACLPermissionMixin
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.file_discovery_service import FileDiscoveryService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

from .utils import (
    annotate_resource,
    build_content_disposition,
    find_resource_in_bundle,
    get_formatted_location,
    get_object_by_pk_or_handle,
    HandleLookupMixin,
    parse_elan_document,
    pick_elan_audio_resource,
    prepare_resource_lists,
    resolve_existing_object,
    resolve_resource_to_presigned,
)


logger = logging.getLogger(__name__)


class BundleDetailView(HandleLookupMixin, ACLPermissionMixin, DetailView):
    """Detail view for a bundle, accessible by UUID or handle."""

    model = Bundle
    template_name = "bundle_detail.html"
    context_object_name = "bundle"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = getattr(self, "acl_result", None)
        service = self.get_acl_service()
        enforcement_enabled = service.enforcement_enabled if service else True
        allowed = True
        if result is not None:
            allowed = result.allowed or not enforcement_enabled
        context["acl_check_result"] = result
        context["can_read_bundle"] = allowed
        context["acl_enforcement_enabled"] = enforcement_enabled

        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            context['collection'] = self.object.structural_info.first().is_member_of_collection

        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
            self.object.geo_location = location.geo_location
            self.object.region_facet = location.region_facet
            self.object.country_facet = location.country_facet
        else:
            self.object.formatted_location = ""
            self.object.geo_location = None
            self.object.region_facet = None
            self.object.country_facet = None

        context['media_resources'] = []
        context['written_resources'] = []
        context['other_resources'] = []
        context['metadata_files'] = []

        if self.object.resources.first():
            resources = self.object.resources.first()
            media_resources, written_resources, other_resources = prepare_resource_lists(resources)
            context['media_resources'] = media_resources
            context['written_resources'] = written_resources
            context['other_resources'] = other_resources

        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            metadata_files = [
                annotate_resource(res)
                for res in self.object.structural_info.first().additional_metadata_files.all()
            ]
            context['metadata_files'] = [res for res in metadata_files if res]

        return context


class BundleResourcesView(View):
    """View for accessing bundle resources directly or listing them."""

    permission_denied_message = _("You do not have permission to access this bundle.")

    def get(self, request, pk=None, handle=None, resource_id=None):
        bundle = get_object_by_pk_or_handle(Bundle, pk=pk, handle=handle)
        acl_service = ACLEvaluationService()
        acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")
        if acl_service.enforcement_enabled and not acl_result.allowed:
            return HttpResponseForbidden(self.permission_denied_message)

        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection

        if resource_id:
            return self._handle_resource_access(request, bundle, resource_id, collection_for_path)

        return self._handle_resource_list(request, bundle, acl_service, acl_result, collection_for_path)

    def _handle_resource_access(self, request, bundle, resource_id, collection_for_path):
        """Handle direct resource access by PID."""
        try:
            decoded_resource_id = unquote(resource_id)

            if decoded_resource_id.startswith('ID_'):
                decoded_resource_id = decoded_resource_id[3:]

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

            add_import_location(
                getattr(bundle, 'import_bucket', None),
                getattr(bundle, 'import_object_key', None),
            )
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
                except Exception:
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

    def _handle_resource_list(self, request, bundle, acl_service, acl_result, collection_for_path):
        """Handle resource list view."""
        context = {
            'bundle': bundle,
            'media_resources': [],
            'written_resources': [],
            'other_resources': [],
            'metadata_files': [],
            'restricted_resources': False,
        }
        context['acl_check_result'] = acl_result
        can_read = acl_result.allowed or not acl_service.enforcement_enabled
        context['can_read_bundle'] = can_read
        context['acl_enforcement_enabled'] = acl_service.enforcement_enabled

        resources = bundle.resources.first()
        if can_read and resources:
            media_resources, written_resources, other_resources = prepare_resource_lists(resources)
            context['media_resources'] = media_resources
            context['written_resources'] = written_resources
            context['other_resources'] = other_resources
        elif resources:
            context['restricted_resources'] = True

        struct_info_manager = getattr(bundle, 'structural_info', None)
        structural_info = struct_info_manager.first() if struct_info_manager else None
        if structural_info:
            context['collection'] = structural_info.is_member_of_collection
            metadata_files = [annotate_resource(res) for res in structural_info.additional_metadata_files.all()]
            metadata_files = [res for res in metadata_files if res]
            if not can_read:
                metadata_files = []
            context['metadata_files'] = metadata_files

        return render(request, 'bundle_resources.html', context)


class ResourceAccessView(View):
    """View for accessing resources either through direct download or streaming."""

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
        action = request.GET.get('action', 'download')
        if action == 'analyze':
            action = 'play'

        try:
            resource = find_resource_in_bundle(bundle, resource_id=resource_id)

            if not resource:
                raise Http404(f"Resource with id {resource_id} not found in bundle {bundle_id}")

            mime_type = getattr(resource, 'mime_type', None)
            normalized_mime_type = mime_type.lower().strip() if mime_type else ''
            extension = (
                Path(getattr(resource, 'file_name', '')).suffix.lower().lstrip('.')
                if getattr(resource, 'file_name', None)
                else ''
            )
            is_elan = extension in {'eaf', 'elan'} or normalized_mime_type == 'text/x-eaf+xml'

            resource_service = ResourceMappingService()

            storage_resolution = resolve_resource_to_presigned(
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

            detected_media_type = determine_media_type(mime_type, getattr(resource, 'file_name', None))
            source_mime_type = guess_source_mime_type(mime_type, getattr(resource, 'file_name', None), detected_media_type)

            elan_context = None
            if is_elan:
                elan_context = self._build_elan_context(
                    resource_service, bundle, resource, collection_for_path,
                    bucket_name, object_key
                )

            download_headers = {
                'ResponseContentDisposition': build_content_disposition(
                    getattr(resource, 'file_name', None)
                ),
            }
            if source_mime_type:
                download_headers['ResponseContentType'] = source_mime_type

            download_url = resource_service.generate_presigned_url(
                bucket_name,
                object_key,
                response_headers=download_headers,
            )

            is_htmx = request.headers.get('HX-Request') == 'true'

            if is_htmx and action in {'play', 'view'}:
                return self._render_htmx_modal(
                    request, resource, mime_type, detected_media_type, source_mime_type,
                    presigned_url, download_url, elan_context, is_elan
                )

            if action == 'download':
                return redirect(download_url)

            if detected_media_type in {'audio', 'video'}:
                if action == 'play':
                    return render(
                        request,
                        'resource_player.html',
                        {
                            'resource_name': resource.file_name,
                            'mime_type': mime_type,
                            'media_type': detected_media_type,
                            'source_mime_type': source_mime_type,
                            'stream_url': presigned_url,
                            'download_url': download_url,
                        },
                    )
                return redirect(presigned_url)

            elif detected_media_type in {'image', 'pdf'}:
                return redirect(presigned_url)
            else:
                return redirect(download_url)

        except ValueError as e:
            logger.error(f"Resource mapping service error: {e}")
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error(f"Error accessing resource: {e}")
            return HttpResponse(f"Error accessing resource: {str(e)}", status=500)

    def _build_elan_context(
        self, resource_service, bundle, resource, collection_for_path,
        bucket_name, object_key
    ):
        """Build ELAN-specific context data."""
        elan_data = parse_elan_document(
            resource_service,
            bucket_name,
            object_key,
        )

        audio_resource = pick_elan_audio_resource(
            bundle,
            resource,
            elan_data,
        )

        audio_url = None
        audio_file_name = None
        if audio_resource:
            audio_resolution = resolve_resource_to_presigned(
                resource_service,
                audio_resource,
                bundle,
                collection_for_path,
            )
            if audio_resolution:
                audio_url = audio_resolution['url']
                audio_file_name = getattr(audio_resource, 'file_name', '')

        return {
            'annotations': elan_data.get('annotations', []),
            'media_files': elan_data.get('media_files', []),
            'audio_url': audio_url,
            'audio_file_name': audio_file_name,
            'tier_headers': elan_data.get('tier_headers', []),
        }

    def _render_htmx_modal(
        self, request, resource, mime_type, detected_media_type, source_mime_type,
        presigned_url, download_url, elan_context, is_elan
    ):
        """Render the HTMX modal response for play/view actions."""
        media_type = 'elan' if is_elan else detected_media_type

        modal_context = {
            'resource_name': resource.file_name,
            'resource_description': getattr(resource, 'file_description', ''),
            'mime_type': mime_type,
            'media_type': media_type,
            'source_mime_type': source_mime_type,
            'stream_url': presigned_url if media_type in {'audio', 'video'} else None,
            'preview_url': presigned_url,
            'download_url': download_url,
            'elan_context': elan_context,
        }

        response = render(
            request,
            'explorer/partials/resource_modal_content.html',
            modal_context,
        )
        response['HX-Trigger'] = json.dumps({'showResourceModal': True})
        return response


class BundleJsonLdView(View):
    """Export bundle metadata as JSON-LD."""

    def get_queryset(self):
        return Bundle.objects.prefetch_related(
            "header",
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__object_languages__alternative_names",
            "general_info__object_languages__taxonomy",
            "general_info__object_languages__taxonomy__language_family",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "publication_info__identifiers",
            "administrative_info",
            "administrative_info__licenses",
            "administrative_info__rights_holders",
            "administrative_info__rights_holders__rights_holder_identifiers",
            "administrative_info__is_identical_to",
            "structural_info",
            "structural_info__bundle_topics",
            "structural_info__is_member_of_collection",
            "structural_info__is_member_of_collection__general_info",
            "structural_info__additional_metadata_files",
        )

    def get(self, request, pk=None, handle=None):
        queryset = self.get_queryset()
        if pk is not None:
            bundle = queryset.filter(pk=pk).first()
        elif handle is not None:
            bundle = queryset.filter(identifier=handle).first()
        else:
            raise Http404("No bundle identifier provided")

        if bundle is None:
            raise Http404("Bundle not found")

        serializer = BundleJsonLdSerializer(bundle)
        data = serializer.serialize()

        response = JsonResponse(data, json_dumps_params={"indent": 2, "ensure_ascii": False})
        response["Content-Type"] = "application/ld+json"

        # Only force download if explicitly requested (not AJAX/fetch)
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        is_fetch = "fetch" in request.headers.get("Sec-Fetch-Mode", "")

        if not is_ajax and not is_fetch:
            general_info = bundle.general_info.first()
            if general_info and general_info.display_title:
                filename = general_info.display_title.replace(" ", "_")[:50]
            else:
                filename = str(bundle.id)[:8]
            response["Content-Disposition"] = f'attachment; filename="{filename}.jsonld"'

        return response


class BundleXmlView(View):
    """Export bundle metadata as BLAM XML."""

    def get(self, request, pk=None, handle=None):
        queryset = Bundle.objects.prefetch_related(
            "header",
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__object_languages__alternative_names",
            "general_info__object_languages__taxonomy",
            "general_info__object_languages__taxonomy__language_family",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "publication_info__identifiers",
            "administrative_info",
            "administrative_info__licenses",
            "administrative_info__rights_holders",
            "administrative_info__rights_holders__rights_holder_identifiers",
            "administrative_info__is_identical_to",
            "structural_info",
            "structural_info__bundle_topics",
            "structural_info__additional_metadata_files",
        )

        if pk is not None:
            bundle = queryset.filter(pk=pk).first()
        elif handle is not None:
            bundle = queryset.filter(identifier=handle).first()
        else:
            raise Http404("No bundle identifier provided")

        if bundle is None:
            raise Http404("Bundle not found")

        exporter = BundleExporter()
        xml_content = exporter.export(bundle)

        general_info = bundle.general_info.first()
        if general_info and general_info.display_title:
            filename = general_info.display_title.replace(" ", "_")[:50]
        else:
            filename = str(bundle.id)[:8]

        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{filename}.xml"'
        return response
