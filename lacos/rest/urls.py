from django.urls import path
from . import views

app_name = "rest"

urlpatterns = [
    # S3 direct upload endpoints
    path("s3/upload/url/", views.get_upload_url, name="get_upload_url"),
    path("s3/upload/batch-urls/", views.get_batch_upload_urls, name="get_batch_upload_urls"),
    path("s3/upload/accelerated-url/", views.get_accelerated_upload_url, name="get_accelerated_upload_url"),
    path("s3/upload/complete/", views.mark_upload_complete, name="mark_upload_complete"),
    
    # S3 object management endpoints
    path("s3/object/copy/", views.copy_object, name="copy_object"),
]
