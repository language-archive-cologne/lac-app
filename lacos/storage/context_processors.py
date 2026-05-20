"""Template context helpers for exposing storage configuration to the UI."""

from django.conf import settings

from lacos.storage.download_config import download_package_max_bytes
from lacos.storage.download_config import format_bytes
from lacos.storage.permissions import is_archivist
from lacos.storage.permissions import is_collection_manager


def upload_client_config(request):
    """Expose storage-related settings used by upload and download UI."""
    cfg = getattr(settings, "MULTIPART_UPLOAD_SETTINGS", {}) or {}

    # Defaults mirror arkumu-app so both dashboards behave the same.
    default_chunk = 100 * 1024 * 1024
    default_concurrency = 8
    default_part_concurrency = 6
    default_threshold = 5 * 1024 * 1024 * 1024  # Prefer single uploads up to 5GB

    threshold_bytes = int(cfg.get("multipart_threshold", default_threshold))
    package_max_bytes = download_package_max_bytes()

    return {
        "UPLOAD_CLIENT_CONFIG": {
            "chunk_size": int(cfg.get("chunk_size", default_chunk)),
            "max_concurrency": int(cfg.get("max_concurrency", default_concurrency)),
            "part_upload_concurrency": int(
                cfg.get("part_upload_concurrency", default_part_concurrency),
            ),
            "multipart_threshold": threshold_bytes,
            "multipart_threshold_label": format_bytes(threshold_bytes),
            "max_retries": int(cfg.get("max_retries", 3)),
            "retry_delay_base": float(cfg.get("retry_delay_base", 0.5)),
        },
        "DOWNLOAD_CLIENT_CONFIG": {
            "package_max_bytes": package_max_bytes,
            "package_max_bytes_label": format_bytes(package_max_bytes),
        },
    }


def navbar_access(request):
    """Expose navbar visibility flags derived from access rules."""
    user = getattr(request, "user", None)

    is_authenticated = bool(getattr(user, "is_authenticated", False))
    can_access_storage = is_collection_manager(user) or is_archivist(user)
    can_access_blam = is_archivist(user) or (
        is_authenticated and bool(getattr(user, "is_staff", False))
    )
    can_access_acl = is_archivist(user)
    can_access_dbadmin = is_authenticated and bool(getattr(user, "is_superuser", False))
    can_access_admin = is_authenticated and bool(getattr(user, "is_staff", False))

    return {
        "NAVBAR_ACCESS": {
            "show_manage_group": any(
                [can_access_storage, can_access_blam, can_access_acl],
            ),
            "show_storage": can_access_storage,
            "show_blam": can_access_blam,
            "show_acl": can_access_acl,
            "show_system_group": can_access_dbadmin or can_access_admin,
            "show_dbadmin": can_access_dbadmin,
            "show_admin": can_access_admin,
        },
    }
