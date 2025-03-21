from django.urls import path

from . import views
from .views import direct_upload_views

app_name = "storage"

urlpatterns = [
    path("upload/", views.upload_form, name="upload_form"),
    path("upload/process/", views.process_upload, name="process_upload"),
    path('mark-uploads-complete/', views.mark_uploads_complete, name='mark_uploads_complete'),
    path("upload/direct/", views.direct_upload, name="direct_upload"),
    path("upload/success/", views.upload_success, name="upload_success"),
    path('upload/complete/', views.upload_complete, name='upload_complete'),
    
    
    # Presigned URL API endpoints
    path("presigned-urls/", views.get_presigned_urls, name="get_presigned_urls"),
    path("verify-uploads/", views.mark_uploads_complete, name="mark_uploads_complete"),
    
    # Archivist dashboard
    path("dashboard/", views.archivist_dashboard, name="archivist_dashboard"),
    
    # File operations
    path("move-to-production/<path:folder_path>/", views.move_to_production, name="move_to_production"),
    path("file-content/<str:bucket_type>/<path:file_path>/", views.file_content, name="file_content"),
    path("delete/<str:bucket_type>/<str:object_type>/<path:object_path>/", views.delete_object, name="delete_object"),
    path("debug/presigned-url/", direct_upload_views.debug_presigned_url, name="debug_presigned_url"),
    path("upload/debug-error/", direct_upload_views.debug_upload_error, name="debug_upload_error"),
] 