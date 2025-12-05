"""
Backward compatibility shim for dashboard views.

This module re-exports views from the new modular structure to maintain
backward compatibility with existing URL patterns and imports.

DEPRECATED: Import from dashboard.archivist, dashboard.acl, or dashboard.htmx.bucket instead.
"""

# Archivist views
from .dashboard.archivist import (
    archivist_dashboard,
    load_folder_contents,
    dashboard_content,
    bucket_size_info,
)

# ACL views
from .dashboard.acl import (
    acl_admin_dashboard,
    acl_load_all,
    acl_load_single,
    acl_save_all,
    acl_save_single,
    acl_update_settings,
    acl_update_permission,
    acl_edit_permission_form,
)
# Backwards compatibility
acl_sync_all = acl_load_all

# HTMX bucket views
from .dashboard.htmx.bucket import (
    BucketContentHTMXView,
    BucketSelectHTMXView,
    CreateBucketHTMXView,
    delete_bucket_htmx,
    RenameBucketModalHTMXView,
    RenameObjectModalHTMXView,
    RenameBucketHTMXView,
    file_info_htmx,
)

__all__ = [
    # Archivist
    "archivist_dashboard",
    "load_folder_contents",
    "dashboard_content",
    "bucket_size_info",
    # ACL
    "acl_admin_dashboard",
    "acl_load_all",
    "acl_load_single",
    "acl_save_all",
    "acl_save_single",
    "acl_sync_all",  # backwards compat
    "acl_update_settings",
    "acl_update_permission",
    "acl_edit_permission_form",
    # HTMX
    "BucketContentHTMXView",
    "BucketSelectHTMXView",
    "CreateBucketHTMXView",
    "delete_bucket_htmx",
    "RenameBucketModalHTMXView",
    "RenameObjectModalHTMXView",
    "RenameBucketHTMXView",
    "file_info_htmx",
]
