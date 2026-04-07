from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse
from xml.etree import ElementTree

from django.conf import settings
from django.db import transaction
from huey.contrib.djhuey import task

try:
    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task
    HUEY_PERIODIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency guard
    HUEY_PERIODIC_AVAILABLE = False

from lacos.common.periodic_task_tracker import tracked_periodic

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


def _run_refresh_metadata() -> dict:
    """Shared SAML metadata refresh logic used by both manual and periodic tasks."""
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


@task(retries=3, retry_delay=60)
def refresh_shibboleth_metadata() -> dict:
    return _run_refresh_metadata()


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(
        crontab(
            minute=getattr(settings, "SAML_METADATA_REFRESH_CRON_MINUTE", 5),
            hour=getattr(settings, "SAML_METADATA_REFRESH_CRON_HOUR", 3),
        )
    )
    @tracked_periodic(
        task_name="periodic_saml_metadata",
        description="SAML Metadata Refresh (periodic)",
        schedule="5 3 * * *",
    )
    def refresh_shibboleth_metadata_periodic() -> dict:
        return _run_refresh_metadata()
else:
    def refresh_shibboleth_metadata_periodic() -> dict:  # pragma: no cover - fallback
        return _run_refresh_metadata()


# ---------------------------------------------------------------------------
# eduGAIN IdP discovery index
# ---------------------------------------------------------------------------

EDUGAIN_METADATA_URL = (
    "https://www.aai.dfn.de/fileadmin/metadata/dfn-aai-edugain+idp-metadata.xml"
)
DFN_AAI_METADATA_URL = (
    "https://www.aai.dfn.de/fileadmin/metadata/dfn-aai-basic-metadata.xml"
)

NS_MD = "urn:oasis:names:tc:SAML:2.0:metadata"
NS_MDUI = "urn:oasis:names:tc:SAML:metadata:ui"

COUNTRY_CORRECTIONS = {"UK": "GB"}
COUNTRY_WHITELIST = {"EU": "European Union", "UK": "United Kingdom"}

_ISO_CODES: set[str] | None = None


def _iso_country_codes() -> set[str]:
    global _ISO_CODES
    if _ISO_CODES is None:
        import pycountry
        _ISO_CODES = {c.alpha_2 for c in pycountry.countries}
    return _ISO_CODES


def _country_name(code: str) -> str:
    if code in COUNTRY_WHITELIST:
        return COUNTRY_WHITELIST[code]
    import pycountry
    country = pycountry.countries.get(alpha_2=code)
    return country.name if country else code


def _extract_country_code(entity_id: str) -> str | None:
    try:
        hostname = urlparse(entity_id).hostname or ""
    except Exception:
        return None
    tld = hostname.rsplit(".", 1)[-1].upper() if hostname else None
    if not tld:
        return None
    tld = COUNTRY_CORRECTIONS.get(tld, tld)
    if tld in _iso_country_codes() or tld in COUNTRY_WHITELIST:
        return tld
    return None


def _extract_display_name(entity: ElementTree.Element) -> str | None:
    # Try MDUI DisplayName (prefer English)
    for idpsso in entity.iter(f"{{{NS_MD}}}IDPSSODescriptor"):
        for ext in idpsso.iter(f"{{{NS_MDUI}}}UIInfo"):
            names = ext.findall(f"{{{NS_MDUI}}}DisplayName")
            en_name = None
            first_name = None
            for n in names:
                text = (n.text or "").strip()
                if not text:
                    continue
                if first_name is None:
                    first_name = text
                lang = n.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                if lang == "en":
                    en_name = text
            if en_name:
                return en_name
            if first_name:
                return first_name

    # Fallback to Organization DisplayName
    for org in entity.iter(f"{{{NS_MD}}}Organization"):
        names = org.findall(f"{{{NS_MD}}}OrganizationDisplayName")
        en_name = None
        first_name = None
        for n in names:
            text = (n.text or "").strip()
            if not text:
                continue
            if first_name is None:
                first_name = text
            lang = n.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            if lang == "en":
                en_name = text
        if en_name:
            return en_name
        if first_name:
            return first_name

    return None


def _extract_logo(entity: ElementTree.Element) -> str:
    best_url = ""
    best_width = -1
    for idpsso in entity.iter(f"{{{NS_MD}}}IDPSSODescriptor"):
        for ext in idpsso.iter(f"{{{NS_MDUI}}}UIInfo"):
            for logo in ext.findall(f"{{{NS_MDUI}}}Logo"):
                url = (logo.text or "").strip()
                if not url:
                    continue
                try:
                    width = int(logo.get("width", "0"))
                except ValueError:
                    width = 0
                if width > best_width:
                    best_width = width
                    best_url = url
    return best_url


def _parse_edugain_metadata(payload: bytes) -> list[dict]:
    idps = []
    for _event, elem in ElementTree.iterparse(BytesIO(payload), events=("end",)):
        if not elem.tag.endswith("EntityDescriptor"):
            continue
        # Only process IdPs
        if elem.find(f"{{{NS_MD}}}IDPSSODescriptor") is None:
            elem.clear()
            continue

        entity_id = elem.get("entityID", "")
        display_name = _extract_display_name(elem)
        if not entity_id or not display_name:
            elem.clear()
            continue

        idps.append({
            "entity_id": entity_id,
            "display_name": display_name,
            "logo": _extract_logo(elem),
            "country_code": _extract_country_code(entity_id),
        })
        elem.clear()
    return idps


def _fetch_metadata(url: str, timeout: int) -> bytes | None:
    logger.info("Fetching metadata from %s", url)
    req = request.Request(url, headers={"User-Agent": "lacos-edugain-index"})
    try:
        with request.urlopen(req, timeout=max(timeout, 60)) as response:
            return response.read()
    except Exception as exc:
        logger.error("Failed to fetch metadata from %s: %s", url, exc, exc_info=True)
        return None


def _run_index_edugain() -> dict:
    if not getattr(settings, "SAML_LOGIN_ENABLED", False):
        return {"success": False, "skipped": "saml_login_disabled"}

    timeout = _get_timeout_seconds()
    urls = [
        str(getattr(settings, "EDUGAIN_METADATA_URL", EDUGAIN_METADATA_URL)),
        str(getattr(settings, "DFN_AAI_METADATA_URL", DFN_AAI_METADATA_URL)),
    ]

    # Merge IdPs from all feeds; first occurrence wins (eduGAIN first).
    merged: dict[str, dict] = {}
    for url in urls:
        payload = _fetch_metadata(url, timeout)
        if not payload:
            logger.warning("Skipping empty/failed metadata from %s", url)
            continue
        logger.info("Parsing metadata (%d bytes) from %s", len(payload), url)
        for idp_data in _parse_edugain_metadata(payload):
            if idp_data["entity_id"] not in merged:
                merged[idp_data["entity_id"]] = idp_data

    if not merged:
        return {"success": False, "error": "all_feeds_empty"}

    idps = list(merged.values())
    logger.info("Found %d unique IdPs across %d feeds", len(idps), len(urls))

    from lacos.users.models import SamlCountry, SamlIdp

    country_cache: dict[str, SamlCountry] = {}
    seen_entity_ids: set[str] = set()

    with transaction.atomic():
        for idp_data in idps:
            seen_entity_ids.add(idp_data["entity_id"])
            country_code = idp_data["country_code"]
            country_obj = None

            if country_code:
                if country_code not in country_cache:
                    country_obj, _ = SamlCountry.objects.update_or_create(
                        code=country_code,
                        defaults={"name": _country_name(country_code)},
                    )
                    country_cache[country_code] = country_obj
                else:
                    country_obj = country_cache[country_code]

            SamlIdp.objects.update_or_create(
                entity_id=idp_data["entity_id"],
                defaults={
                    "display_name": idp_data["display_name"],
                    "logo": idp_data["logo"],
                    "country": country_obj,
                },
            )

        deleted_count, _ = SamlIdp.objects.exclude(
            entity_id__in=seen_entity_ids
        ).delete()
        if deleted_count:
            logger.info("Removed %d stale IdPs from discovery index", deleted_count)

    return {"success": True, "indexed": len(idps), "removed": deleted_count if 'deleted_count' in dir() else 0}


@task(retries=3, retry_delay=120)
def index_edugain_idps(tracking_id: str | None = None) -> dict:
    from lacos.storage.services.background_task_service import BackgroundTaskService

    if tracking_id:
        BackgroundTaskService.mark_running(tracking_id, message="Fetching eduGAIN metadata")
    try:
        result = _run_index_edugain()
    except Exception as exc:
        if tracking_id:
            BackgroundTaskService.mark_failed(tracking_id, error_message=str(exc))
        raise
    if tracking_id:
        if result.get("success"):
            BackgroundTaskService.mark_success(
                tracking_id,
                message=f"Indexed {result.get('indexed', 0)} IdPs",
                result=result,
            )
        else:
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=result.get("error", "unknown"),
                result=result,
            )
    return result


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(
        crontab(
            minute=getattr(settings, "EDUGAIN_INDEX_CRON_MINUTE", 30),
            hour=getattr(settings, "EDUGAIN_INDEX_CRON_HOUR", 3),
        )
    )
    @tracked_periodic(
        task_name="periodic_edugain_index",
        description="eduGAIN IdP Discovery Index (periodic)",
        schedule="30 3 * * *",
    )
    def index_edugain_idps_periodic() -> dict:
        return _run_index_edugain()
else:
    def index_edugain_idps_periodic() -> dict:  # pragma: no cover - fallback
        return _run_index_edugain()
