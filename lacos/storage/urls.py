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
    
    # Multipart upload API endpoints
    path("multipart/initialize/", views.initialize_multipart_upload, name="initialize_multipart_upload"),
    path("multipart/get-part-urls/", views.get_part_upload_urls, name="get_part_upload_urls"),
    path("multipart/complete/", views.complete_multipart_upload, name="complete_multipart_upload"),
    path("multipart/abort/", views.abort_multipart_upload, name="abort_multipart_upload"),
    path("multipart/list/", views.list_multipart_uploads, name="list_multipart_uploads"),
    
    # Archivist dashboard
    path("dashboard/", views.archivist_dashboard, name="archivist_dashboard"),
    path("dashboard/folder-contents/<str:bucket_type>/<path:folder_path>/", views.load_folder_contents, name="load_folder_contents"),
    
    # File operations
    path("file-content/<str:bucket_type>/<path:file_path>/", views.file_content, name="file_content"),
    path("delete/<str:bucket_type>/<str:object_type>/<path:object_path>/", views.delete_object, name="delete_object"),
    path("htmx/rename-object/<str:bucket_name>/<str:object_type>/<path:object_path>/", views.RenameObjectHTMXView.as_view(), name="rename_object_htmx"),
    path("htmx/rename-bucket-modal/<str:bucket_name>/", views.RenameBucketModalHTMXView.as_view(), name="rename_bucket_modal_htmx"),
    path("htmx/rename-object-modal/<str:bucket_name>/<str:object_type>/<path:object_path>/", views.RenameObjectModalHTMXView.as_view(), name="rename_object_modal_htmx"),
    path("debug/presigned-url/", direct_upload_views.debug_presigned_url, name="debug_presigned_url"),
    path("upload/debug-error/", direct_upload_views.debug_upload_error, name="debug_upload_error"),

    # Add new route for dashboard content partials
    path("dashboard-content/<str:bucket_type>/", views.dashboard_content, name="dashboard_content"),

    # HTMX bucket operations
    path("htmx/bucket-content/<str:bucket_name>/", views.BucketContentHTMXView.as_view(), name="bucket_content_htmx"),
    path("htmx/create-bucket/", views.CreateBucketHTMXView.as_view(), name="create_bucket_htmx"),
    path("htmx/delete-bucket/<str:bucket_name>/", views.delete_bucket_htmx, name="delete_bucket_htmx"),
    path("htmx/rename-bucket/<str:bucket_name>/", views.RenameBucketHTMXView.as_view(), name="rename_bucket_htmx"),

    # OCFL conversion operations
    path("ocfl/modal/<str:bucket_name>/<path:folder_path>/", views.ocfl_conversion_modal, name="ocfl_conversion_modal"),
    path("ocfl/convert/<str:bucket_name>/<path:folder_path>/", views.ConvertToOCFLView.as_view(), name="convert_to_ocfl"),
] 
