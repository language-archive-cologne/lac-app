from types import SimpleNamespace
from unittest.mock import MagicMock

from lacos.explorer.views.utils.storage import resolve_resource_to_presigned


def test_resolve_resource_to_presigned_syncs_resolved_location(monkeypatch):
    """Resolved fallback bucket/key should be synced to S3ResourceLocation."""
    resource = SimpleNamespace(
        id="resource-1",
        file_name="burung_KOW.imdi",
        file_pid="hdl:11341/0000-0000-0000-3D03",
    )
    bundle = SimpleNamespace(
        id="bundle-1",
        import_bucket=None,
        import_object_key=None,
    )

    service = MagicMock()
    service.production_bucket = "grails-dev"
    service.resolve_pid_to_s3.return_value = None
    service.generate_presigned_url.return_value = "https://example.test/presigned"

    monkeypatch.setattr(
        "lacos.explorer.views.utils.storage.resolve_existing_object",
        lambda _service, _candidates: (
            "grails-dev",
            "wooi_archive_cologne/burung_kow/v1/content/Resources/burung_KOW.imdi",
        ),
    )

    result = resolve_resource_to_presigned(
        service,
        resource,
        bundle,
        collection_for_path=None,
    )

    assert result is not None
    assert result["bucket"] == "grails-dev"
    assert result["key"].endswith("burung_KOW.imdi")
    assert result["url"] == "https://example.test/presigned"
    service.register_s3_location.assert_called_once_with(
        resource,
        "grails-dev",
        "wooi_archive_cologne/burung_kow/v1/content/Resources/burung_KOW.imdi",
        pid_url="hdl:11341/0000-0000-0000-3D03",
        fetch_metadata=False,
    )
