from django.urls import path

from . import views

app_name = "storage"

urlpatterns = [
    path("upload/", views.upload_form, name="upload_form"),
    path("upload/process/", views.upload_form, name="upload_folder"),
    path("upload/success/", views.upload_success, name="upload_success"),
    
    # Archivist dashboard
    path("dashboard/", views.archivist_dashboard, name="archivist_dashboard"),
    
    # File operations
    path("move-to-production/<path:folder_path>/", views.move_to_production, name="move_to_production"),
    path("file-content/<str:bucket_type>/<path:file_path>/", views.file_content, name="file_content"),
    path("delete/<str:bucket_type>/<str:object_type>/<path:object_path>/", views.delete_object, name="delete_object"),
    
    # API-based operations
    path("copy-to-production/", views.copy_object_to_production, name="copy_to_production"),
] 