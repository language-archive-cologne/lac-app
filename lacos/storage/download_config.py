"""Download limits shared by download views and templates."""

from django.conf import settings

DEFAULT_DOWNLOAD_PACKAGE_MAX_BYTES = 500 * 1024 * 1024
BYTES_PER_KIB = 1024


def format_bytes(size_bytes: int) -> str:
    """Return a compact binary size label for user-facing messages."""
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= BYTES_PER_KIB and unit_index < len(units) - 1:
        size /= BYTES_PER_KIB
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    if size.is_integer():
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def positive_int_setting(name: str, default: int) -> int:
    """Read a positive integer setting with a defensive fallback."""
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def download_package_max_bytes() -> int:
    """Return the configured maximum size for browser-built TAR packages."""
    return positive_int_setting(
        "DOWNLOAD_PACKAGE_MAX_BYTES",
        DEFAULT_DOWNLOAD_PACKAGE_MAX_BYTES,
    )
