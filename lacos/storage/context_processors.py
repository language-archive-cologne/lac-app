"""Template context helpers for exposing storage upload configuration to the UI."""

from django.conf import settings

from lacos.storage.permissions import is_archivist, is_collection_manager


def upload_client_config(request):
    """Expose upload-related settings so the dashboard JS can tune multipart behaviour."""
    cfg = getattr(settings, "MULTIPART_UPLOAD_SETTINGS", {}) or {}

    # Defaults mirror the tuned values used in arkumu-app so both dashboards behave the same
    default_chunk = 100 * 1024 * 1024  # 100MB chunks reduce HTTP overhead for large files
    default_concurrency = 8
    default_part_concurrency = 6
    default_threshold = 5 * 1024 * 1024 * 1024  # Prefer single uploads up to 5GB

    def format_bytes(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(size_bytes)
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        if size.is_integer():
            return f"{int(size)} {units[unit_index]}"
        return f"{size:.1f} {units[unit_index]}"

    threshold_bytes = int(cfg.get("multipart_threshold", default_threshold))

    return {
        "UPLOAD_CLIENT_CONFIG": {
            "chunk_size": int(cfg.get("chunk_size", default_chunk)),
            "max_concurrency": int(cfg.get("max_concurrency", default_concurrency)),
            "part_upload_concurrency": int(
                cfg.get("part_upload_concurrency", default_part_concurrency)
            ),
            "multipart_threshold": threshold_bytes,
            "multipart_threshold_label": format_bytes(threshold_bytes),
            "max_retries": int(cfg.get("max_retries", 3)),
            "retry_delay_base": float(cfg.get("retry_delay_base", 0.5)),
        }
    }


def navbar_access(request):
    """Expose navbar visibility flags derived from the same access rules as the views."""
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
                [can_access_storage, can_access_blam, can_access_acl]
            ),
            "show_storage": can_access_storage,
            "show_blam": can_access_blam,
            "show_acl": can_access_acl,
            "show_system_group": can_access_dbadmin or can_access_admin,
            "show_dbadmin": can_access_dbadmin,
            "show_admin": can_access_admin,
        }
    }
