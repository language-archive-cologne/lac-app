import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from lacos.storage.services.bucket_service import BucketService
from django.http import HttpResponse

logger = logging.getLogger(__name__)


@login_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing both ingest and production buckets.
    Only loads root level items initially for better performance.
    """
    bucket_service = BucketService()
    
    try:
        # Get only root level items for both buckets
        ingest_structure = bucket_service.get_root_level_items(bucket_service.ingest_bucket)
        production_structure = bucket_service.get_root_level_items(bucket_service.production_bucket)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        # Return empty structures on error
        ingest_structure = {"type": "folder", "name": bucket_service.ingest_bucket, "path": "", "children": []}
        production_structure = {"type": "folder", "name": bucket_service.production_bucket, "path": "", "children": []}
    
    # Check for success message
    message = request.GET.get('message', None)
    
    return render(
        request,
        "dashboard/archivist_dashboard.html",
        {
            "ingest_structure": ingest_structure,
            "production_structure": production_structure,
            "message": message,
        },
    )

@login_required
def load_folder_contents(request, bucket_type, folder_path):
    """
    Load contents of a specific folder when expanded.
    """
    bucket_service = BucketService()
    bucket = bucket_service.ingest_bucket if bucket_type == 'ingest' else bucket_service.production_bucket
    
    try:
        # Clean up the folder path to handle double slashes
        folder_path = folder_path.replace('//', '/')
        logger.info(f"Loading folder contents for {bucket_type} bucket, path: {folder_path}")
        
        # Get folder contents
        folder_contents = bucket_service.get_folder_contents(bucket, folder_path)
        logger.info(f"Folder contents for {folder_path}: {folder_contents}")
        
    except Exception as e:
        logger.error(f"Error loading folder contents for {folder_path}: {str(e)}")
        # Return empty list on error
        folder_contents = []
    
    return render(
        request,
        "dashboard/folder_contents_partial.html",
        {
            "folder_contents": folder_contents,
            "bucket_type": bucket_type,
            "folder_path": folder_path,
        },
    )

@login_required
def dashboard_content(request, bucket_type):
    """
    Return only the structure content for a specific bucket type.
    This is used for AJAX/HTMX refreshes of just one section of the dashboard.
    
    Args:
        bucket_type (str): Either "ingest" or "production"
        
    Returns:
        Rendered partial template with the requested bucket structure
    """
    try:
        bucket_service = BucketService()
        
        if bucket_type == "ingest":
            structure = bucket_service.get_root_level_items(bucket_service.ingest_bucket)
        elif bucket_type == "production":
            structure = bucket_service.get_root_level_items(bucket_service.production_bucket)
        else:
            return HttpResponse("Invalid bucket type", status=400)
            
        logger.info(f"Refreshing {bucket_type} structure with {len(structure.get('children', []))} items")
        
        # Render just the folder structure partial
        return render(
            request,
            "dashboard/folder_structure_partial.html",
            {"structure": structure, "bucket_type": bucket_type}
        )
    except Exception as e:
        logger.exception(f"Error loading dashboard content for {bucket_type}: {str(e)}")
        return HttpResponse(f"Error: {str(e)}", status=500) 