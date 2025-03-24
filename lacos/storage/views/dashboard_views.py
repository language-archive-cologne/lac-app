import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from lacos.storage.services.bucket_service import BucketService

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
        # Get folder contents
        folder_contents = bucket_service.get_folder_contents(bucket, folder_path)
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