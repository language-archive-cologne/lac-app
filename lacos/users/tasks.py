from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from urllib import error, request
from xml.etree import ElementTree

from django.conf import settings
from huey.contrib.djhuey import task

try:
    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task
    HUEY_PERIODIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency guard
    HUEY_PERIODIC_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_METADATA_URL = "https://idp.rrz.uni-koeln.de/idp/shibboleth"


def _get_refresh_url() -> str:
    return str(getattr(settings, "SAML_METADATA_REFRESH_URL", DEFAULT_METADATA_URL))


def _get_refresh_path() -> Path:
    explicit_path = getattr(settings, "SAML_METADATA_REFRESH_PATH", "")
    if explicit_path:
        return Path(explicit_path)

    local_paths = getattr(settings, "SAML_METADATA_LOCAL", None)
    if isinstance(local_paths, (list, tuple)) and local_paths:
        if len(local_paths) > 1:
            logger.warning(
                "Multiple SAML_METADATA_LOCAL entries detected; using %s for refresh.",
                local_paths[0],
            )
        return Path(local_paths[0])

    base_dir = getattr(settings, "BASE_DIR", Path.cwd())
    return Path(base_dir) / "shibboleth.xml"


def _get_timeout_seconds() -> int:
    return int(getattr(settings, "SAML_METADATA_REFRESH_TIMEOUT_SECONDS", 15))


def _get_expected_entity_id() -> str | None:
    expected = str(getattr(settings, "SAML_METADATA_REFRESH_EXPECTED_ENTITY_ID", "")).strip()
    return expected or None


def _load_existing_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
    except OSError as exc:
        logger.warning("Unable to read existing SAML metadata from %s: %s", path, exc)
        return None
    return hashlib.sha256(data).hexdigest()


def _validate_metadata(payload: bytes, expected_entity_id: str | None) -> None:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("metadata is not valid XML") from exc

    if not root.tag.endswith("EntityDescriptor") and not root.tag.endswith("EntitiesDescriptor"):
        raise ValueError("metadata root element is not SAML metadata")

    if expected_entity_id:
        for element in root.iter():
            if element.tag.endswith("EntityDescriptor"):
                if element.get("entityID") == expected_entity_id:
                    return
        raise ValueError(
            f"metadata does not include expected entityID {expected_entity_id!r}"
        )


def _write_metadata(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_mode = None
    if path.exists():
        try:
            existing_mode = path.stat().st_mode & 0o777
        except OSError:
            existing_mode = None

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(path.parent)) as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_path = Path(tmp_file.name)

        os.replace(tmp_path, path)
        if existing_mode is not None:
            os.chmod(path, existing_mode)
    finally:
        if tmp_path and tmp_path.exists() and tmp_path != path:
            try:
                tmp_path.unlink()
            except OSError:
                logger.debug("Unable to remove temporary metadata file %s", tmp_path)


@task(retries=3, retry_delay=60)
def refresh_shibboleth_metadata() -> dict:
    if not getattr(settings, "SAML_LOGIN_ENABLED", False):
        return {"success": False, "skipped": "saml_login_disabled"}

    if not getattr(settings, "SAML_METADATA_REFRESH_ENABLED", True):
        return {"success": False, "skipped": "refresh_disabled"}

    url = _get_refresh_url()
    target_path = _get_refresh_path()
    timeout = _get_timeout_seconds()
    expected_entity_id = _get_expected_entity_id()

    logger.info("Fetching SAML metadata from %s", url)

    request_obj = request.Request(url, headers={"User-Agent": "lacos-saml-metadata-refresh"})
    try:
        with request.urlopen(request_obj, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise error.HTTPError(url, status, "HTTP error", hdrs=response.headers, fp=None)
            payload = response.read()
    except Exception as exc:
        logger.error("Failed to fetch SAML metadata from %s: %s", url, exc, exc_info=True)
        return {"success": False, "error": "fetch_failed", "detail": str(exc)}

    if not payload:
        logger.error("Empty SAML metadata response from %s", url)
        return {"success": False, "error": "empty_response"}

    try:
        _validate_metadata(payload, expected_entity_id)
    except ValueError as exc:
        logger.error("Invalid SAML metadata from %s: %s", url, exc)
        return {"success": False, "error": "invalid_metadata", "detail": str(exc)}

    new_hash = hashlib.sha256(payload).hexdigest()
    existing_hash = _load_existing_hash(target_path)

    if existing_hash == new_hash:
        logger.info("SAML metadata unchanged; keeping existing file at %s", target_path)
        return {"success": True, "changed": False, "path": str(target_path)}

    try:
        _write_metadata(target_path, payload)
    except OSError as exc:
        logger.error("Failed to write SAML metadata to %s: %s", target_path, exc, exc_info=True)
        return {"success": False, "error": "write_failed", "detail": str(exc)}

    logger.info("Updated SAML metadata at %s", target_path)
    return {"success": True, "changed": True, "path": str(target_path)}


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(
        crontab(
            minute=getattr(settings, "SAML_METADATA_REFRESH_CRON_MINUTE", 5),
            hour=getattr(settings, "SAML_METADATA_REFRESH_CRON_HOUR", 3),
        )
    )
    def refresh_shibboleth_metadata_periodic() -> dict:
        return refresh_shibboleth_metadata()
else:
    def refresh_shibboleth_metadata_periodic() -> dict:  # pragma: no cover - fallback
        return refresh_shibboleth_metadata()
