from __future__ import annotations

from collections.abc import Sequence

DEFAULT_MDQ_URL = "https://mdq.aai.dfn.de/"


def build_saml_metadata_sources(
    *,
    local_paths: Sequence[str] | None,
    remote_urls: Sequence[str] | None,
    mdq_url: str | None,
    mdq_cert_file: str | None = None,
    fallback_local_path: str | None = None,
) -> dict[str, list]:
    metadata: dict[str, list] = {}

    normalized_local_paths = [
        path.strip()
        for path in (local_paths or [])
        if isinstance(path, str) and path.strip()
    ]
    if normalized_local_paths:
        metadata["local"] = normalized_local_paths

    normalized_remote_urls = [
        {"url": url.strip()}
        for url in (remote_urls or [])
        if isinstance(url, str) and url.strip()
    ]
    if normalized_remote_urls:
        metadata["remote"] = normalized_remote_urls

    normalized_mdq_url = (mdq_url or "").strip()
    if normalized_mdq_url:
        mdq_entry = {"url": normalized_mdq_url}
        normalized_cert_file = (mdq_cert_file or "").strip()
        if normalized_cert_file:
            mdq_entry["cert"] = normalized_cert_file
        metadata["mdq"] = [mdq_entry]

    normalized_fallback_path = (fallback_local_path or "").strip()
    if not metadata and normalized_fallback_path:
        metadata["local"] = [normalized_fallback_path]

    return metadata
