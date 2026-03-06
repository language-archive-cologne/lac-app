import logging
import json
import unicodedata
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from lacos.storage.permissions import can_manage_collection, resolve_collection_from_path
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse, QueryDict
from django.utils.decorators import method_decorator
from django.views import View
from django.template.loader import render_to_string
from django.middleware.csrf import get_token
from django.urls import reverse

from lacos.storage.services.bucket_service import BucketService
from lacos.common.mixins.htmx_template_helpers import HtmxTemplateHelperMixin

logger = logging.getLogger(__name__)


@login_required
def file_content(request, bucket_type, file_path):
    """
    Retrieve and display the content of a file from a bucket.
    
    This view serves the content of a file directly to the browser.
    For binary files (images, etc.), it streams the content with the
    appropriate content type. For text files, it renders the content
    in a readable format.
    """
    collection = resolve_collection_from_path(file_path)
    if not can_manage_collection(request.user, collection):
        raise PermissionDenied("Collection manager access required.")

    try:
        bucket_service = BucketService()

        # Use the bucket_type parameter directly as the bucket name
        bucket = bucket_type

        # Get file content and metadata
        result = bucket_service.get_file_content(bucket, file_path)

        if "error" not in result:
            metadata = result.get("metadata", {})
            content_type = metadata.get("content_type", "application/octet-stream")
            content = result.get("content")
            
            # Return the file content with the appropriate content type
            response = HttpResponse(content, content_type=content_type)
            
            # Add content disposition header for download if requested
            if request.GET.get("download") == "true":
                filename = file_path.split("/")[-1]
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                
            return response
        else:
            error_message = f"Failed to retrieve file: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            return HttpResponse(error_message, status=404)
            
    except Exception as e:
        error_message = f"Error retrieving file content: {str(e)}"
        logger.exception(error_message)
        return HttpResponse(error_message, status=500)


@login_required
def file_viewer_htmx(request, bucket_type, object_path):
    """Return modal content with a presigned URL for streaming file previews."""
    collection = resolve_collection_from_path(object_path)
    if not can_manage_collection(request.user, collection):
        raise PermissionDenied("Collection manager access required.")
    bucket_service = BucketService()

    accessible_buckets = set(bucket_service.get_all_accessible_buckets())

    if bucket_type in accessible_buckets:
        bucket_name = bucket_type
    elif bucket_type == "ingest":
        bucket_name = bucket_service.ingest_bucket
    elif bucket_type == "production":
        bucket_name = bucket_service.production_bucket
    else:
        return HttpResponse(status=404)

    info_result = bucket_service.get_file_info(bucket_name, object_path)

    if not info_result.get("success", False):
        html = render_to_string(
            "dashboard/partials/file_viewer_error.html",
            {
                "file_name": object_path.rstrip("/").split("/")[-1],
                "error": info_result.get("error", "Unable to load file metadata."),
            },
            request=request,
        )
        return HttpResponse(html, status=404)

    presigned = bucket_service.generate_presigned_download_url(bucket_name, object_path)

    if not presigned.get("success", False):
        html = render_to_string(
            "dashboard/partials/file_viewer_error.html",
            {
                "file_name": info_result.get("file_name"),
                "error": presigned.get("error", "Could not generate access link."),
            },
            request=request,
        )
        return HttpResponse(html, status=500)

    content_type = info_result.get("content_type") or "application/octet-stream"
    file_name = info_result.get("file_name") or object_path.rstrip("/").split("/")[-1]

    viewer_type = _determine_viewer_type(content_type, file_name)

    # Resolve pre-computed audio visualization sidecars only for WAV previews.
    requested_player_mode = (request.GET.get("player_mode") or "simple").lower()
    if requested_player_mode not in {"simple", "analyze"}:
        requested_player_mode = "simple"

    peaks_url = None
    spectrogram_data_url = None
    spectrogram_available = False
    lowered_type = content_type.lower()
    file_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    is_wav_audio = viewer_type == "audio" and (
        file_ext == "wav"
        or lowered_type in {"audio/wav", "audio/x-wav", "audio/wave"}
    )
    if is_wav_audio:
        peaks_key = f"{object_path}.peaks.json"
        peaks_info = bucket_service.get_file_info(bucket_name, peaks_key)
        if peaks_info.get("success"):
            peaks_presigned = bucket_service.generate_presigned_download_url(bucket_name, peaks_key)
            if peaks_presigned.get("success"):
                peaks_url = peaks_presigned["url"]

        spectrogram_data_key = f"{object_path}.spectrogram.bin"
        spectrogram_data_info = bucket_service.get_file_info(bucket_name, spectrogram_data_key)
        spectrogram_available = bool(spectrogram_data_info.get("success"))

        if requested_player_mode == "analyze":
            if spectrogram_available:
                spectrogram_data_presigned = bucket_service.generate_presigned_download_url(
                    bucket_name,
                    spectrogram_data_key,
                )
                if spectrogram_data_presigned.get("success"):
                    spectrogram_data_url = spectrogram_data_presigned["url"]

    effective_player_mode = "analyze" if spectrogram_data_url else "simple"

    context = {
        "file_name": file_name,
        "filename": file_name,
        "bucket_type": bucket_type,
        "object_path": object_path,
        "content_type": content_type,
        "file_size": info_result.get("file_size"),
        "file_size_formatted": info_result.get("file_size_formatted"),
        "last_modified": info_result.get("last_modified"),
        "etag": info_result.get("etag"),
        "download_url": presigned.get("url"),
        "expires_in": presigned.get("expires_in"),
        "viewer_type": viewer_type,
        "peaks_url": peaks_url,
        "spectrogram_data_url": spectrogram_data_url,
        "player_mode": effective_player_mode,
        "spectrogram_available": spectrogram_available,
    }

    if viewer_type in ("json", "xml"):
        context.update(_fetch_pretty_content(bucket_service, bucket_name, object_path, viewer_type))

    if viewer_type == "markdown":
        context.update(_fetch_markdown_html(bucket_service, bucket_name, object_path))

    html = render_to_string(
        "dashboard/partials/file_viewer_modal.html",
        context,
        request=request,
    )
    return HttpResponse(html)


def _determine_viewer_type(content_type: str, file_name: str) -> str:
    """Infer viewer type from MIME type and extension."""
    if not content_type:
        content_type = "application/octet-stream"

    lowered_type = content_type.lower()
    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    if lowered_type.startswith("video/") or extension in {"mp4", "webm", "mov", "m4v", "avi"}:
        return "video"
    if lowered_type.startswith("audio/") or extension in {"mp3", "wav", "ogg", "flac", "m4a"}:
        return "audio"
    if lowered_type.startswith("image/") or extension in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg"}:
        return "image"
    if extension in {"eaf", "elan"}:
        return "elan"
    if lowered_type == "application/pdf" or extension == "pdf":
        return "pdf"
    if extension == "json" or lowered_type in {"application/json", "application/ld+json"}:
        return "json"
    if extension == "xml" or lowered_type in {"application/xml", "text/xml"}:
        return "xml"
    if extension == "md" or lowered_type == "text/markdown":
        return "markdown"
    if lowered_type.startswith("text/") or extension in {"txt", "html", "csv"}:
        return "text"
    return "download"


def _strip_whitespace_nodes(node):
    """Remove whitespace-only text nodes so minidom doesn't double-indent."""
    remove = []
    for child in node.childNodes:
        if child.nodeType == child.TEXT_NODE and not child.data.strip():
            remove.append(child)
        elif child.hasChildNodes():
            _strip_whitespace_nodes(child)
    for child in remove:
        node.removeChild(child)


def _fetch_pretty_content(bucket_service, bucket_name, object_path, viewer_type):
    """Fetch file content from S3 and pretty-print JSON/XML for in-modal display."""
    import xml.dom.minidom

    MAX_PREVIEW_BYTES = 2 * 1024 * 1024  # 2 MB cap for in-modal rendering

    try:
        result = bucket_service.get_file_content(bucket_name, object_path)
        raw = result.get("content", b"")
        if len(raw) > MAX_PREVIEW_BYTES:
            return {"file_content": None, "language_class": ""}

        text = raw.decode("utf-8", errors="replace")

        if viewer_type == "json":
            parsed = json.loads(text)
            return {
                "file_content": json.dumps(parsed, indent=2, ensure_ascii=False),
                "language_class": "language-json",
            }

        if viewer_type == "xml":
            doc = xml.dom.minidom.parseString(text)
            _strip_whitespace_nodes(doc)
            pretty = doc.toprettyxml(indent="  ")
            # Remove the XML declaration that minidom adds
            lines = pretty.split("\n")
            if lines and lines[0].startswith("<?xml"):
                lines = lines[1:]
            # Remove blank lines
            pretty = "\n".join(line for line in lines if line.strip())
            return {
                "file_content": pretty,
                "language_class": "language-xml",
            }
    except Exception:
        logger.debug("Could not pretty-print %s for preview", object_path, exc_info=True)

    return {"file_content": None, "language_class": ""}


def _fetch_markdown_html(bucket_service, bucket_name, object_path):
    """Fetch a Markdown file from S3 and convert it to HTML for in-modal display."""
    import re
    import markdown as md

    MAX_PREVIEW_BYTES = 2 * 1024 * 1024  # 2 MB cap

    try:
        result = bucket_service.get_file_content(bucket_name, object_path)
        raw = result.get("content", b"")
        if len(raw) > MAX_PREVIEW_BYTES:
            return {"markdown_html": None}

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        text = unicodedata.normalize("NFC", text)
        html = md.markdown(text, extensions=["fenced_code", "tables", "toc", "nl2br"])
        # Strip dangerous tags to prevent XSS from embedded HTML in markdown
        html = re.sub(r"<script[\s>].*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[\s>].*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"\bon\w+\s*=", "", html, flags=re.IGNORECASE)
        return {"markdown_html": html}
    except Exception:
        logger.exception("Could not render markdown %s for preview", object_path)

    return {"markdown_html": None}


@method_decorator(login_required, name='dispatch')
class RenameObjectHTMXView(HtmxTemplateHelperMixin, View):
    """HTMX endpoint for renaming files and folders within a bucket."""

    def post(self, request, bucket_name, object_type, object_path):
        collection = resolve_collection_from_path(object_path)
        if not can_manage_collection(request.user, collection):
            raise PermissionDenied("Collection manager access required.")
        bucket_service = BucketService()

        new_name = (request.POST.get('newName') or request.POST.get('prompt') or '').strip()
        if not new_name and request.body:
            try:
                raw_body = request.body.decode(request.encoding or 'utf-8')
                if request.content_type == 'application/json':
                    payload = json.loads(raw_body)
                    new_name = (payload.get('newName') or payload.get('prompt') or '').strip()
                elif request.content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
                    form_data = QueryDict(raw_body)
                    new_name = (form_data.get('newName') or form_data.get('prompt') or '').strip()
            except (ValueError, TypeError):
                new_name = ''

        current_name = object_path.rstrip('/').split('/')[-1]

        if not new_name:
            error_html = render_to_string(
                'dashboard/partials/rename_object_modal.html',
                {
                    'modal_open': True,
                    'form_action': reverse('storage:rename_object_htmx', args=[bucket_name, object_type, object_path]),
                    'current_name': current_name,
                    'new_name': '',
                    'object_type': object_type,
                    'object_path': object_path,
                    'bucket_name': bucket_name,
                    'error': 'A new name is required',
                    'oob': False,
                    'csrf_token': get_token(request),
                },
                request=request,
            )
            return HttpResponse(error_html, status=400)

        if object_type not in {'file', 'folder'}:
            error_html = render_to_string(
                'dashboard/partials/rename_object_modal.html',
                {
                    'modal_open': True,
                    'form_action': reverse('storage:rename_object_htmx', args=[bucket_name, object_type, object_path]),
                    'current_name': current_name,
                    'new_name': new_name,
                    'object_type': object_type,
                    'object_path': object_path,
                    'bucket_name': bucket_name,
                    'error': 'Invalid object type',
                    'oob': False,
                    'csrf_token': get_token(request),
                },
                request=request,
            )
            return HttpResponse(error_html, status=400)

        if object_type == 'folder':
            result = bucket_service.rename_folder(bucket_name, object_path, new_name)
        else:
            result = bucket_service.rename_file(bucket_name, object_path, new_name)

        if not result.get('success'):
            error_html = render_to_string(
                'dashboard/partials/rename_object_modal.html',
                {
                    'modal_open': True,
                    'form_action': reverse('storage:rename_object_htmx', args=[bucket_name, object_type, object_path]),
                    'current_name': current_name,
                    'new_name': new_name,
                    'object_type': object_type,
                    'object_path': object_path,
                    'bucket_name': bucket_name,
                    'error': result.get('error', 'Rename failed'),
                    'oob': False,
                    'csrf_token': get_token(request),
                },
                request=request,
            )
            return HttpResponse(error_html, status=400)

        updated_path = result.get('folder_path') or result.get('file_path') or object_path

        content_html = self.render_bucket_content_template(request, bucket_name)
        modal_html = render_to_string(
            'dashboard/partials/rename_object_modal.html',
            {
                'modal_open': False,
                'form_action': reverse('storage:rename_object_htmx', args=[bucket_name, object_type, updated_path]),
                'current_name': new_name,
                'new_name': '',
                'object_type': object_type,
                'object_path': updated_path,
                'bucket_name': bucket_name,
                'error': None,
                'oob': True,
                'csrf_token': get_token(request),
            },
            request=request,
        )

        return HttpResponse(content_html + modal_html)


@login_required
def delete_object(request, bucket_type, object_type, object_path):
    """
    Delete a file or folder from a bucket.
    
    This operation permanently deletes the specified object from the bucket.
    If the object is a folder, all contents will also be deleted.
    
    Args:
        bucket_type: "ingest" or "production"
        object_type: "file" or "folder"
        object_path: The path to the object within the bucket
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})

    if object_type not in {"file", "folder"}:
        return JsonResponse({"success": False, "error": "Invalid object type"}, status=400)
    
    collection = resolve_collection_from_path(object_path)
    if not can_manage_collection(request.user, collection):
        return JsonResponse({"success": False, "error": "Collection manager access required."}, status=403)

    try:
        bucket_service = BucketService()
        
        accessible_buckets = bucket_service.get_all_accessible_buckets()
        if isinstance(accessible_buckets, (list, tuple, set)) and bucket_type in accessible_buckets:
            bucket_name = bucket_type
        elif bucket_type == 'ingest':
            bucket_name = bucket_service.ingest_bucket
        elif bucket_type == 'production':
            bucket_name = bucket_service.production_bucket
        else:
            bucket_name = bucket_type
        
        # Delete the object based on its type
        if object_type == "folder":
            result = bucket_service.delete_folder(bucket_name, object_path)
        else:  # file
            result = bucket_service.delete_file(bucket_name, object_path)
        
        if result.get("success", False):
            success_message = f"Successfully deleted {object_type} '{object_path}'"
            logger.info(success_message)
            messages.success(request, success_message)
            
            if request.headers.get('HX-Request') == 'true':
                # Return an empty response with 200 OK instead of 204 No Content
                return HttpResponse("", status=200)  # Empty string but status 200
            
            return JsonResponse({"success": True, "message": success_message})
        else:
            error_message = f"Failed to delete {object_type}: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            
            if request.headers.get('HX-Request') == 'true':
                return HttpResponse(error_message, status=400)
                
            return JsonResponse({"success": False, "error": error_message})
            
    except Exception as e:
        error_message = f"Error deleting {object_type}: {str(e)}"
        logger.exception(error_message)
        messages.error(request, error_message)
        
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse(error_message, status=500)
            
        return JsonResponse({"success": False, "error": error_message}) 
