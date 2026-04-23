from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import RedirectView

from . import views
from .views.download_views import (
    AltchaChallengeView,
    ProtectedDownloadView,
    BundleDownloadView,
    BundleScriptDownloadView,
)

app_name = "storage"

urlpatterns = [
    path("", views.archivist_dashboard, name="archivist_dashboard"),
    path('mark-uploads-complete/', views.mark_uploads_complete, name='mark_uploads_complete'),
    
    
    # Presigned URL API endpoints
    path("presigned-urls/", views.get_presigned_urls, name="get_presigned_urls"),
    path("verify-uploads/", views.mark_uploads_complete, name="mark_uploads_complete"),
    
    # Multipart upload API endpoints
    path("multipart/initialize/", views.initialize_multipart_upload, name="initialize_multipart_upload"),
    path("multipart/get-part-urls/", views.get_part_upload_urls, name="get_part_upload_urls"),
    path("multipart/complete/", views.complete_multipart_upload, name="complete_multipart_upload"),
    path("multipart/abort/", views.abort_multipart_upload, name="abort_multipart_upload"),
    path("multipart/list/", views.list_multipart_uploads, name="list_multipart_uploads"),

    # Metadata ingestion
    path("ingest/metadata/", views.ingest_metadata, name="ingest_metadata"),
    path("ingest/metadata/preview/", views.preview_metadata_ingest, name="preview_metadata_ingest"),
    path("ingest/metadata/modal/<str:bucket_type>/<str:object_type>/<path:object_path>/",
         views.metadata_ingest_modal,
         name="metadata_ingest_modal"),
    path("validate/metadata/<str:bucket_type>/<path:object_path>/",
         views.validate_metadata_endpoint,
         name="validate_metadata"),

    path("tasks/<uuid:task_id>/status/", views.background_task_status, name="background_task_status"),

    # Archivist dashboard
    path(
        "dashboard/",
        RedirectView.as_view(pattern_name="storage:archivist_dashboard", permanent=False),
        name="archivist_dashboard_legacy_redirect",
    ),
    path("dashboard/folder-contents/<str:bucket_type>/<path:folder_path>/", views.load_folder_contents, name="load_folder_contents"),
    path("dashboard/bucket-size/<str:bucket_name>/", views.bucket_size_info, name="bucket_size_info"),

    # ACL Admin dashboard
    path("dashboard/acl/", views.acl_admin_dashboard, name="acl_admin_dashboard"),
    path("dashboard/acl/panel/", views.acl_dashboard_panel, name="acl_dashboard_panel"),
    path("dashboard/acl/records/", views.acl_records_panel, name="acl_records_panel"),
    path("dashboard/acl/records/<str:scope>/", views.acl_records_table, name="acl_records_table"),
    path("dashboard/acl/load/", views.acl_load_all, name="acl_load_all"),
    path(
        "dashboard/acl/load/collection/<uuid:collection_id>/bundles/",
        views.acl_load_collection_bundles,
        name="acl_load_collection_bundles",
    ),
    path("dashboard/acl/load/selected/", views.acl_load_selected, name="acl_load_selected"),
    path("dashboard/acl/load/<str:object_type>/<str:object_id>/", views.acl_load_single, name="acl_load_single"),
    path("dashboard/acl/save/", views.acl_save_all, name="acl_save_all"),
    path("dashboard/acl/save/<str:object_type>/<str:object_id>/", views.acl_save_single, name="acl_save_single"),
    # Backwards compatibility
    path("dashboard/acl/sync/", views.acl_load_all, name="acl_sync_all"),
    path("dashboard/acl/settings/", views.acl_update_settings, name="acl_update_settings"),
    path("dashboard/acl/permissions/orphans/<str:scope>/", views.acl_delete_orphans, name="acl_delete_orphans"),
    path("dashboard/acl/permissions/update/", views.acl_update_permission, name="acl_update_permission"),
    path("dashboard/acl/permissions/edit/<str:object_type>/<str:object_id>/", views.acl_edit_permission_form, name="acl_edit_permission_form"),
    
    # File operations
    path("file-content/<str:bucket_type>/<path:file_path>/", views.file_content, name="file_content"),
    path(
        "htmx/file-viewer/<str:bucket_type>/<path:object_path>/",
        views.file_viewer_htmx,
        name="file_viewer_htmx",
    ),
    path("delete/<str:bucket_type>/<str:object_type>/<path:object_path>/", views.delete_object, name="delete_object"),
    path("htmx/rename-object/<str:bucket_name>/<str:object_type>/<path:object_path>/", views.RenameObjectHTMXView.as_view(), name="rename_object_htmx"),
    path("htmx/rename-bucket-modal/<str:bucket_name>/", views.RenameBucketModalHTMXView.as_view(), name="rename_bucket_modal_htmx"),
    path("htmx/rename-object-modal/<str:bucket_name>/<str:object_type>/<path:object_path>/", views.RenameObjectModalHTMXView.as_view(), name="rename_object_modal_htmx"),
    # Add new route for dashboard content partials
    path("dashboard-content/<str:bucket_type>/", views.dashboard_content, name="dashboard_content"),

    # HTMX bucket operations
    path("htmx/bucket-content/<str:bucket_name>/", views.BucketContentHTMXView.as_view(), name="bucket_content_htmx"),
    path("htmx/bucket-select/", views.BucketSelectHTMXView.as_view(), name="bucket_select_htmx"),
    path("htmx/create-bucket/", views.CreateBucketHTMXView.as_view(), name="create_bucket_htmx"),
    path("htmx/delete-bucket/<str:bucket_name>/", views.delete_bucket_htmx, name="delete_bucket_htmx"),
    path("htmx/rename-bucket/<str:bucket_name>/", views.RenameBucketHTMXView.as_view(), name="rename_bucket_htmx"),
    path("htmx/file-info/<str:bucket_type>/<path:object_path>/", views.file_info_htmx, name="file_info_htmx"),

    # OCFL conversion operations
    path("ocfl/modal/<str:bucket_name>/<path:folder_path>/", views.ocfl_conversion_modal, name="ocfl_conversion_modal"),
    path("ocfl/convert/<str:bucket_name>/<path:folder_path>/", views.ConvertToOCFLView.as_view(), name="convert_to_ocfl"),

    # Audio peaks generation
    path("peaks/modal/<str:bucket_name>/", views.generate_peaks_modal, name="generate_peaks_modal"),
    path("peaks/modal/<str:bucket_name>/<path:folder_path>/", views.generate_peaks_modal, name="generate_peaks_folder_modal"),
    path("peaks/generate/<str:bucket_name>/", views.GeneratePeaksView.as_view(), name="generate_peaks"),
    path("peaks/generate/<str:bucket_name>/<path:folder_path>/", views.GeneratePeaksView.as_view(), name="generate_peaks_folder"),

    # ALTCHA and protected downloads
    # Note: CSRF exempt because these endpoints use ALTCHA proof-of-work for protection
    # and only return presigned URLs (no state modification)
    path("altcha/challenge/", AltchaChallengeView.as_view(), name="altcha_challenge"),
    path("download/", csrf_exempt(ProtectedDownloadView.as_view()), name="protected_download"),
    path("download/bundle/", csrf_exempt(BundleDownloadView.as_view()), name="bundle_download"),
    path("download/scripts/", csrf_exempt(BundleScriptDownloadView.as_view()), name="bundle_script_download"),
] 
