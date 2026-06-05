"""Storage view entrypoints.

The package intentionally keeps a single import surface (`storage.views`) while
routing canonical dashboard handlers through modularized implementations.
"""

from .dashboard_views import *
from .dashboard.archivist import archivist_dashboard, dashboard_content, load_folder_contents, bucket_size_info
from .dashboard.acl import (
    acl_admin_dashboard,
    acl_load_all,
    acl_load_collection_bundles,
    acl_load_selected,
    acl_load_single,
    acl_save_all,
    acl_save_single,
    acl_update_settings,
    acl_sync_scope_fields,
    acl_update_permission,
    acl_bulk_update_bundle_readers,
    acl_edit_permission_form,
)
acl_sync_all = acl_load_all
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
from .presigned_url_views import *
from .file_operations_views import *
from .ocfl_conversion_views import *
from .generate_peaks_views import *
from .metadata_ingest_views import *
from .background_task_views import *

# This file marks the directory as a Python package
