import logging
import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
    try:
        bucket_service = BucketService()

        # Use the bucket_type parameter directly as the bucket name
        bucket = bucket_type

        # Get file content and metadata
        result = bucket_service.get_file_content(bucket, file_path)
        
        if result.get("success", False):
            content_type = result.get("content_type", "application/octet-stream")
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
    }

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
    if lowered_type.startswith("text/") or extension in {"txt", "json", "xml", "html", "csv", "md"}:
        return "text"
    return "download"


@method_decorator(login_required, name='dispatch')
class RenameObjectHTMXView(HtmxTemplateHelperMixin, View):
    """HTMX endpoint for renaming files and folders within a bucket."""

    def post(self, request, bucket_name, object_type, object_path):
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
