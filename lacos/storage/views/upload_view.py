import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.urls import reverse

# Import views from their respective modules
from lacos.storage.views.presigned_url_views import get_presigned_urls, mark_uploads_complete
from lacos.storage.views.dashboard_views import archivist_dashboard
from lacos.storage.views.direct_upload_views import direct_upload, process_upload

logger = logging.getLogger(__name__)


@login_required
def upload_form(request):
    """
    Render the upload form for uploading folders to the ingest bucket.
    
    This is a simple view that renders the upload form HTML template.
    No business logic is performed here.
    """
    return render(request, "upload/upload_form.html")


@login_required
def upload_success(request):
    """
    Render the upload success page.
    
    This is a simple view that renders the success confirmation template.
    No business logic is performed here.
    """
    return render(request, "upload/upload_success.html")
