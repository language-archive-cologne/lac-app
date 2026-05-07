"""Bundle views for the explorer app."""

import json
import logging
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import unquote

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView

from lacos.blam.models import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.blam.mappers.bundle.write.bundle_exporter import BundleExporter
from lacos.blam.serializers import BundleJsonLdSerializer
from lacos.explorer.media_utils import determine_media_type, guess_source_mime_type
from lacos.explorer.permissions import (
    ACLPermissionMixin,
    MetadataExposureMixin,
    build_forbidden_response,
    enforce_binary_exposure,
)
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.exposure_policy_service import ExposurePolicyService
from lacos.storage.services.file_discovery_service import FileDiscoveryService
from lacos.storage.services.media_processing_service import MediaProcessingService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

from .utils import (
    annotate_resource,
    build_s3_location_lookup,
    build_content_disposition,
    find_resource_in_bundle,
    find_subtitle_for_video,
    get_formatted_location,
    get_object_by_pk_or_handle,
    HandleLookupMixin,
    is_imdi_resource,
    load_markdown_preview,
    load_xml_preview,
    parse_elan_document,
    pick_elan_audio_resource,
    prepare_resource_lists,
    render_imdi_modal_response,
    resolve_existing_object,
    resolve_resource_to_presigned,
)


logger = logging.getLogger(__name__)


def _iter_bundle_detail_resources(resources_container, structural_info=None):
    if resources_container:
        yield from resources_container.bundle_media_resources.all()
        yield from resources_container.bundle_written_resources.all()
        yield from resources_container.bundle_other_resources.all()
    if structural_info:
        yield from structural_info.additional_metadata_files.all()


class BundleLookupPermissionMixin(ACLPermissionMixin):
    _resolved_bundle = None

    def get_bundle_queryset(self):
        raise NotImplementedError

    def get_bundle(self, pk=None, handle=None):
        if self._resolved_bundle is not None:
            return self._resolved_bundle

        queryset = self.get_bundle_queryset()
        if pk is not None:
            bundle = queryset.filter(pk=pk).first()
        elif handle is not None:
            bundle = queryset.filter(identifier=handle).first()
            if bundle is None and not handle.startswith("hdl:"):
                bundle = queryset.filter(identifier=f"hdl:{handle}").first()
        else:
            raise Http404("No bundle identifier provided")

        if bundle is None:
            raise Http404("Bundle not found")

        self._resolved_bundle = bundle
        return bundle

    def get_acl_object(self, request, *args, **kwargs):
        return self.get_bundle(
            pk=kwargs.get("pk"),
            handle=kwargs.get("handle"),
        )


class BundleDetailView(MetadataExposureMixin, HandleLookupMixin, ACLPermissionMixin, DetailView):
    """Detail view for a bundle, accessible by UUID or handle."""

    model = Bundle
    template_name = "bundle_detail.html"
    context_object_name = "bundle"
    def get_queryset(self):
        return Bundle.objects.prefetch_related(
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "structural_info",
            "structural_info__additional_metadata_files",
            "administrative_info",
            "administrative_info__licenses",
            "resources",
            "resources__bundle_media_resources",
            "resources__bundle_written_resources",
            "resources__bundle_other_resources",
        )

    def render_to_response(self, context, **response_kwargs):
        """Handle content negotiation for CLARIN infrastructure compatibility.

        Returns CMDI/XML when Accept header requests application/x-cmdi+xml.
        """
        accept = self.request.headers.get('Accept', '')
        if 'application/x-cmdi+xml' in accept:
            return redirect('explorer:bundle_xml_by_handle', handle=self.object.handle_path)

        return super().render_to_response(context, **response_kwargs)

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

        structural_info = None
        if hasattr(self.object, 'structural_info'):
            structural_info = self.object.structural_info.first()
        if structural_info:
            context['collection'] = structural_info.is_member_of_collection

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
        context['restricted_resources'] = False

        resources = self.object.resources.first()
        content_type_cache = {}
        s3_locations_by_resource = build_s3_location_lookup(
            _iter_bundle_detail_resources(resources, structural_info),
            content_type_cache=content_type_cache,
        )
        if allowed and resources:
            media_resources, written_resources, other_resources = prepare_resource_lists(
                resources,
                s3_locations_by_resource=s3_locations_by_resource,
                content_type_cache=content_type_cache,
            )
            context['media_resources'] = media_resources
            context['written_resources'] = written_resources
            context['other_resources'] = other_resources
        elif resources:
            context['restricted_resources'] = True

        if structural_info:
            metadata_files = [
                annotate_resource(
                    res,
                    s3_locations_by_resource=s3_locations_by_resource,
                    content_type_cache=content_type_cache,
                )
                for res in structural_info.additional_metadata_files.all()
            ]
            context['metadata_files'] = [res for res in metadata_files if res]

        # Licenses
        context['licenses'] = []
        if hasattr(self.object, 'administrative_info') and self.object.administrative_info.first():
            context['licenses'] = self.object.administrative_info.first().licenses.all()

        return context


class BundleResourcesView(View):
    """View for accessing bundle resources directly or listing them."""

    permission_denied_message = _("You do not have permission to access this bundle.")

    def get(self, request, pk=None, handle=None, resource_id=None):
        bundle = get_object_by_pk_or_handle(Bundle, pk=pk, handle=handle)
        acl_service = ACLEvaluationService()
        policy = ExposurePolicyService(acl_service=acl_service)
        acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")
        if acl_service.enforcement_enabled and not acl_result.allowed:
            return build_forbidden_response(self.permission_denied_message, request=request)

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

            resource_service = ResourceMappingService(skip_bucket_check=True)
            location = resource_service.resolve_pid_to_s3(decoded_resource_id)
            if not location:
                raise ValueError(f"No S3 location found for PID: {decoded_resource_id}")

            resource_obj = find_resource_in_bundle(bundle, file_pid=decoded_resource_id)
            if resource_obj is None:
                raise Http404(f"Resource {resource_id} not found in bundle")
            denied_response = enforce_binary_exposure(
                request,
                resource_obj,
                denial_message=self.permission_denied_message,
                policy=policy,
            )
            if denied_response is not None:
                return denied_response

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
            logger.error("Resource mapping service error", extra={"error": str(e)})
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error("Error accessing resource", extra={"error": str(e)})
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
        struct_info_manager = getattr(bundle, 'structural_info', None)
        structural_info = struct_info_manager.first() if struct_info_manager else None
        content_type_cache = {}
        s3_locations_by_resource = build_s3_location_lookup(
            _iter_bundle_detail_resources(resources, structural_info),
            content_type_cache=content_type_cache,
        )
        if can_read and resources:
            media_resources, written_resources, other_resources = prepare_resource_lists(
                resources,
                s3_locations_by_resource=s3_locations_by_resource,
                content_type_cache=content_type_cache,
            )
            context['media_resources'] = media_resources
            context['written_resources'] = written_resources
            context['other_resources'] = other_resources
        elif resources:
            context['restricted_resources'] = True

        if structural_info:
            context['collection'] = structural_info.is_member_of_collection
            # Additional metadata files are always public, no ACL check needed
            metadata_files = [
                annotate_resource(
                    res,
                    s3_locations_by_resource=s3_locations_by_resource,
                    content_type_cache=content_type_cache,
                )
                for res in structural_info.additional_metadata_files.all()
            ]
            metadata_files = [res for res in metadata_files if res]
            context['metadata_files'] = metadata_files

        return render(request, 'bundle_resources.html', context)


class ResourceAccessView(View):
    """View for accessing resources either through direct download or streaming."""

    permission_denied_message = _("You do not have permission to access this resource.")

    def get(self, request, bundle_id=None, resource_id=None, handle=None, resource_pid=None):
        policy = ExposurePolicyService()
        # Resolve bundle by UUID or handle
        if bundle_id:
            bundle = get_object_or_404(Bundle, pk=bundle_id)
        elif handle:
            bundle = Bundle.objects.filter(identifier=handle).first()
            if not bundle and not handle.startswith('hdl:'):
                bundle = Bundle.objects.filter(identifier=f"hdl:{handle}").first()
            if not bundle:
                raise Http404(f"Bundle with handle '{handle}' not found")
        else:
            raise Http404("No bundle identifier provided")

        # Resolve resource by UUID or file_pid
        if resource_id:
            resource = find_resource_in_bundle(bundle, resource_id=resource_id)
        elif resource_pid:
            resource = find_resource_in_bundle(bundle, file_pid=resource_pid)
            if not resource and not resource_pid.startswith('hdl:'):
                resource = find_resource_in_bundle(bundle, file_pid=f"hdl:{resource_pid}")
        else:
            resource = None

        # Additional metadata files are always public, skip ACL check for them
        is_additional_metadata = isinstance(resource, BundleAdditionalMetadataFile)
        if is_additional_metadata:
            denied_response = enforce_binary_exposure(
                request,
                resource,
                denial_message=self.permission_denied_message,
                policy=policy,
            )
            if denied_response is not None:
                return denied_response
        else:
            acl_service = ACLEvaluationService()
            acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")
            if acl_service.enforcement_enabled and not acl_result.allowed:
                return build_forbidden_response(self.permission_denied_message, request=request)

        if not resource:
            res_ref = resource_id or resource_pid
            raise Http404(f"Resource '{res_ref}' not found in bundle")

        collection_for_path = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info.first():
            collection_for_path = bundle.structural_info.first().is_member_of_collection
        action = request.GET.get('action', 'view')

        try:

            mime_type = getattr(resource, 'mime_type', None)
            normalized_mime_type = mime_type.lower().strip() if mime_type else ''
            extension = (
                Path(getattr(resource, 'file_name', '')).suffix.lower().lstrip('.')
                if getattr(resource, 'file_name', None)
                else ''
            )
            is_elan = extension in {'eaf', 'elan'} or normalized_mime_type == 'text/x-eaf+xml'

            resource_service = ResourceMappingService(skip_bucket_check=True)

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
            if is_htmx and action in {'play', 'view'} and is_imdi_resource(
                getattr(resource, 'file_name', None),
                mime_type,
            ):
                imdi_modal_response = render_imdi_modal_response(
                    request,
                    s3_client=getattr(resource_service, "s3_client", None),
                    bucket=bucket_name,
                    key=object_key,
                    collection=collection_for_path,
                )
                if imdi_modal_response is not None:
                    return imdi_modal_response

            xml_preview = None
            if is_htmx and action in {'play', 'view'} and detected_media_type == 'xml' and not is_elan:
                xml_preview = load_xml_preview(resource_service, bucket_name, object_key)

            markdown_html = None
            if is_htmx and action in {'play', 'view'} and detected_media_type == 'markdown':
                markdown_html = load_markdown_preview(resource_service, bucket_name, object_key)

            if action == 'download':
                raise Http404("Direct downloads are not available")

            # Resolve precomputed visualization sidecars for audio files
            # Also resolve for ELAN files that have a linked audio resource
            peaks_url = None
            spectrogram_data_url = None
            spectrogram_available = False
            pitch_data_url = None
            pitch_available = False
            sidecar_bucket = None
            sidecar_key = None
            if detected_media_type == 'audio':
                sidecar_bucket = bucket_name
                sidecar_key = object_key
            elif is_elan and elan_context and elan_context.get('audio_bucket'):
                sidecar_bucket = elan_context['audio_bucket']
                sidecar_key = elan_context['audio_key']

            if sidecar_bucket and sidecar_key:
                peaks_url = self._resolve_peaks_url(resource_service, sidecar_bucket, sidecar_key)
                spectrogram_available = self._spectrogram_data_exists(
                    resource_service,
                    sidecar_bucket,
                    sidecar_key,
                )
                if action == 'analyze':
                    if spectrogram_available:
                        spectrogram_data_url = resource_service.generate_presigned_url(
                            sidecar_bucket,
                            MediaProcessingService._derivative_s3_key(sidecar_key, ".spectrogram.bin"),
                        )
                pitch_available = self._pitch_data_exists(
                    resource_service, sidecar_bucket, sidecar_key,
                )
                pitch_data_url = None
                if action == 'pitch' and pitch_available:
                    pitch_data_url = resource_service.generate_presigned_url(
                        sidecar_bucket,
                        MediaProcessingService._derivative_s3_key(sidecar_key, ".pitch.bin"),
                    )
            player_mode = 'simple'
            if sidecar_bucket and sidecar_key:
                if action == 'pitch' and pitch_data_url:
                    player_mode = 'pitch'
                elif action == 'analyze' and bool(spectrogram_data_url):
                    player_mode = 'analyze'

            subtitle_url = None
            if detected_media_type == 'video':
                subtitle_url = find_subtitle_for_video(
                    bundle, resource, resource_service, collection_for_path,
                )

            resource_play_url = f"{request.path}?action=play"
            resource_analyze_url = f"{request.path}?action=analyze"
            resource_pitch_url = f"{request.path}?action=pitch"

            if is_htmx and action in {'play', 'view', 'analyze', 'pitch'}:
                return self._render_htmx_modal(
                    request, resource, mime_type, detected_media_type, source_mime_type,
                    presigned_url, download_url, elan_context, is_elan,
                    xml_preview=xml_preview,
                    markdown_html=markdown_html,
                    download_bucket=bucket_name,
                    download_key=object_key,
                    peaks_url=peaks_url,
                    spectrogram_data_url=spectrogram_data_url,
                    player_mode=player_mode,
                    spectrogram_available=spectrogram_available,
                    pitch_data_url=pitch_data_url,
                    pitch_available=pitch_available,
                    resource_play_url=resource_play_url,
                    resource_analyze_url=resource_analyze_url,
                    resource_pitch_url=resource_pitch_url,
                    subtitle_url=subtitle_url,
                )

            if action in {'play', 'view', 'analyze', 'pitch'}:
                return self._render_resource_page(
                    request, resource, bundle, mime_type,
                    detected_media_type, source_mime_type,
                    presigned_url, download_url, elan_context, is_elan,
                    xml_preview=xml_preview,
                    markdown_html=markdown_html,
                    download_bucket=bucket_name,
                    download_key=object_key,
                    peaks_url=peaks_url,
                    spectrogram_data_url=spectrogram_data_url,
                    player_mode=player_mode,
                    spectrogram_available=spectrogram_available,
                    pitch_data_url=pitch_data_url,
                    pitch_available=pitch_available,
                    resource_play_url=resource_play_url,
                    resource_analyze_url=resource_analyze_url,
                    resource_pitch_url=resource_pitch_url,
                    subtitle_url=subtitle_url,
                )

            raise Http404("Unsupported action")

        except ValueError as e:
            logger.error("Resource mapping service error", extra={"error": str(e)})
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error("Error accessing resource", extra={"error": str(e)})
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
        audio_bucket = None
        audio_key = None
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
                audio_bucket = audio_resolution['bucket']
                audio_key = audio_resolution['key']

        return {
            'annotations': elan_data.get('annotations', []),
            'media_files': elan_data.get('media_files', []),
            'audio_url': audio_url,
            'audio_file_name': audio_file_name,
            'audio_bucket': audio_bucket,
            'audio_key': audio_key,
            'tier_headers': elan_data.get('tier_headers', []),
        }

    def _render_htmx_modal(
        self, request, resource, mime_type, detected_media_type, source_mime_type,
        presigned_url, download_url, elan_context, is_elan,
        xml_preview=None,
        markdown_html=None,
        download_bucket=None,
        download_key=None,
        peaks_url=None,
        spectrogram_data_url=None,
        player_mode='simple',
        spectrogram_available=False,
        pitch_data_url=None,
        pitch_available=False,
        resource_play_url=None,
        resource_analyze_url=None,
        resource_pitch_url=None,
        subtitle_url=None,
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
            'download_bucket': download_bucket,
            'download_key': download_key,
            'download_filename': getattr(resource, 'file_name', None),
            'elan_context': elan_context,
            'xml_content': xml_preview,
            'markdown_html': markdown_html,
            'peaks_url': peaks_url,
            'spectrogram_data_url': spectrogram_data_url,
            'player_mode': player_mode,
            'spectrogram_available': spectrogram_available,
            'pitch_data_url': pitch_data_url,
            'pitch_available': pitch_available,
            'resource_play_url': resource_play_url,
            'resource_analyze_url': resource_analyze_url,
            'resource_pitch_url': resource_pitch_url,
            'subtitle_url': subtitle_url,
        }

        response = render(
            request,
            'explorer/partials/resource_modal_content.html',
            modal_context,
        )
        response['HX-Trigger'] = json.dumps({'showResourceModal': True})
        return response

    def _render_resource_page(
        self, request, resource, bundle, mime_type, detected_media_type,
        source_mime_type, presigned_url, download_url, elan_context, is_elan,
        **kwargs,
    ):
        """Render a standalone resource landing page."""
        media_type = 'elan' if is_elan else detected_media_type

        context = {
            'resource_name': resource.file_name,
            'resource_description': getattr(resource, 'file_description', ''),
            'mime_type': mime_type,
            'media_type': media_type,
            'source_mime_type': source_mime_type,
            'stream_url': presigned_url if media_type in {'audio', 'video'} else None,
            'preview_url': presigned_url,
            'download_url': download_url,
            'download_bucket': kwargs.get('download_bucket'),
            'download_key': kwargs.get('download_key'),
            'download_filename': getattr(resource, 'file_name', None),
            'elan_context': elan_context,
            'xml_content': kwargs.get('xml_preview'),
            'markdown_html': kwargs.get('markdown_html'),
            'peaks_url': kwargs.get('peaks_url'),
            'spectrogram_data_url': kwargs.get('spectrogram_data_url'),
            'player_mode': kwargs.get('player_mode', 'simple'),
            'spectrogram_available': kwargs.get('spectrogram_available', False),
            'pitch_data_url': kwargs.get('pitch_data_url'),
            'pitch_available': kwargs.get('pitch_available', False),
            'resource_play_url': kwargs.get('resource_play_url'),
            'resource_analyze_url': kwargs.get('resource_analyze_url'),
            'resource_pitch_url': kwargs.get('resource_pitch_url'),
            'subtitle_url': kwargs.get('subtitle_url'),
            'bundle': bundle,
            'resource': resource,
        }

        return render(request, 'resource_detail.html', context)

    def _resolve_peaks_url(self, resource_service, bucket_name, object_key):
        """Check if pre-computed peaks exist and return a presigned URL."""
        peaks_key = MediaProcessingService._derivative_s3_key(object_key, ".peaks.json")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=peaks_key)
            return resource_service.generate_presigned_url(bucket_name, peaks_key)
        except Exception:
            return None

    def _resolve_spectrogram_data_url(self, resource_service, bucket_name, object_key):
        """Check if pre-computed spectrogram frequencies exist and return a presigned URL."""
        spectrogram_data_key = MediaProcessingService._derivative_s3_key(object_key, ".spectrogram.bin")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=spectrogram_data_key)
            return resource_service.generate_presigned_url(bucket_name, spectrogram_data_key)
        except Exception:
            return None

    def _spectrogram_data_exists(self, resource_service, bucket_name, object_key):
        """Check if pre-computed spectrogram sidecar exists."""
        spectrogram_data_key = MediaProcessingService._derivative_s3_key(object_key, ".spectrogram.bin")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=spectrogram_data_key)
            return True
        except Exception:
            return False

    def _pitch_data_exists(self, resource_service, bucket_name, object_key):
        """Check if pre-computed pitch sidecar exists."""
        pitch_key = MediaProcessingService._derivative_s3_key(object_key, ".pitch.bin")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=pitch_key)
            return True
        except Exception:
            return False


class ResourceByHandleView(View):
    """Resolve a flat resource handle to its resource landing page.

    Supports the direct URL pattern: /resource/<handle_id>/
    e.g. /resource/11341/00-0000-0000-0000-1B28-A
    which maps to file_pid = "hdl:11341/00-0000-0000-0000-1B28-A"
    """

    def get(self, request, handle_id):
        file_pid = f"hdl:{handle_id}"

        # Search across all bundle resource types.
        for model in (MediaResource, WrittenResource, OtherResource, BundleAdditionalMetadataFile):
            resource = model.objects.filter(file_pid=file_pid).first()
            if resource:
                if isinstance(resource, BundleAdditionalMetadataFile):
                    bundle = Bundle.objects.filter(
                        structural_info__additional_metadata_files=resource
                    ).first()
                else:
                    # Reverse path goes through BundleResources (M2M container) → Bundle.resources
                    bundle = Bundle.objects.filter(
                        resources__in=resource.bundleresources_set.all()
                    ).first()
                if bundle:
                    # Render directly via ResourceAccessView
                    view = ResourceAccessView()
                    return view.get(
                        request,
                        handle=bundle.identifier,
                        resource_pid=file_pid,
                    )

        raise Http404(f"Resource with handle '{file_pid}' not found")


class BundleJsonLdView(MetadataExposureMixin, BundleLookupPermissionMixin, View):
    """Export bundle metadata as JSON-LD."""

    def get_bundle_queryset(self):
        return Bundle.objects.prefetch_related(
            "header",
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__object_languages__alternative_names",
            "general_info__object_languages__bundle_object_language_taxonomy",
            "general_info__object_languages__bundle_object_language_taxonomy__language_family",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "administrative_info",
            "administrative_info__licenses",
            "administrative_info__rights_holders",
            "administrative_info__rights_holders__rights_holder_identifiers",
            "administrative_info__is_identical_to",
            "structural_info",
            "structural_info__is_member_of_collection",
            "structural_info__is_member_of_collection__general_info",
            "structural_info__additional_metadata_files",
        )

    def get(self, request, pk=None, handle=None):
        bundle = self.get_bundle(pk=pk, handle=handle)

        serializer = BundleJsonLdSerializer(bundle)
        data = serializer.serialize()

        if request.headers.get("HX-Request") == "true":
            from django.core.serializers.json import DjangoJSONEncoder
            content = json.dumps(data, indent=2, ensure_ascii=False, cls=DjangoJSONEncoder)
            return render(request, "explorer/partials/metadata_preview.html", {
                "content": content,
                "language_class": "language-json",
            })

        response = JsonResponse(data, json_dumps_params={"indent": 2, "ensure_ascii": False})
        response["Content-Type"] = "application/ld+json"

        general_info = bundle.general_info.first()
        if general_info and general_info.display_title:
            filename = general_info.display_title.replace(" ", "_")[:50]
        else:
            filename = str(bundle.id)[:8]
        response["Content-Disposition"] = f'attachment; filename="{filename}.jsonld"'

        return response


class BundleXmlView(MetadataExposureMixin, BundleLookupPermissionMixin, View):
    """Export bundle metadata as BLAM XML."""

    def get_bundle_queryset(self):
        return Bundle.objects.prefetch_related(
            "header",
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__object_languages__alternative_names",
            "general_info__object_languages__bundle_object_language_taxonomy",
            "general_info__object_languages__bundle_object_language_taxonomy__language_family",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "administrative_info",
            "administrative_info__licenses",
            "administrative_info__rights_holders",
            "administrative_info__rights_holders__rights_holder_identifiers",
            "administrative_info__is_identical_to",
            "structural_info",
            "structural_info__additional_metadata_files",
        )

    def get(self, request, pk=None, handle=None):
        bundle = self.get_bundle(pk=pk, handle=handle)

        exporter = BundleExporter()
        try:
            xml_content = exporter.export(bundle)
        except Exception as e:
            logger.exception("Failed to export bundle %s as XML", bundle.identifier)
            msg = f"Error generating XML for bundle {bundle.identifier}: {e}"
            if request.headers.get("HX-Request") == "true":
                return render(request, "explorer/partials/metadata_preview.html", {
                    "content": msg,
                    "language_class": "language-plain",
                })
            return HttpResponse(msg, content_type="text/plain", status=500)

        if request.headers.get("HX-Request") == "true":
            return render(request, "explorer/partials/metadata_preview.html", {
                "content": xml_content,
                "language_class": "language-xml",
            })

        general_info = bundle.general_info.first()
        if general_info and general_info.display_title:
            filename = general_info.display_title.replace(" ", "_")[:50]
        else:
            filename = str(bundle.id)[:8]

        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{filename}.xml"'
        return response
