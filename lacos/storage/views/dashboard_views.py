import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@login_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing both ingest and production buckets.
    
    This view displays the folder structure of both buckets side by side,
    allowing the archivist to view, move, and manage files between buckets.
    """
    bucket_service = BucketService()
    
    # Get folder structure for both buckets
    ingest_structure = bucket_service.get_folder_structure(bucket_service.ingest_bucket)
    production_structure = bucket_service.get_folder_structure(bucket_service.production_bucket)
    
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