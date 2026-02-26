import json

import pytest
from django.urls import reverse

from lacos.blam.models import Collection

HTTP_OK = 200


class _FakeImdiStorageService:
    def discover_imdi_files(self, bucket: str, prefix: str) -> list[str]:
        del bucket, prefix
        return ["archive/corpus.imdi"]

    def find_root_imdi(self, keys: list[str], prefix: str) -> str | None:
        del prefix
        return keys[0] if keys else None


@pytest.mark.django_db
def test_imdi_browser_htmx_returns_modal_content(client, monkeypatch):
    collection = Collection.objects.create(
        identifier="hdl:11341/imdi-modal",
        import_bucket="test-bucket",
        import_object_key="archive/corpus.imdi",
    )

    monkeypatch.setattr(
        "lacos.explorer.views.imdi._get_storage_service",
        lambda: _FakeImdiStorageService(),
    )

    response = client.get(
        reverse("explorer:imdi_browser", kwargs={"pk": collection.pk}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == HTTP_OK
    page = response.content.decode("utf-8")
    assert "data-imdi-viewer" in page
    assert "data-modal-close" in page

    trigger_payload = json.loads(response["HX-Trigger"])
    assert trigger_payload == {"showResourceModal": True}


@pytest.mark.django_db
def test_imdi_browser_non_htmx_returns_full_page(client, monkeypatch):
    collection = Collection.objects.create(
        identifier="hdl:11341/imdi-page",
        import_bucket="test-bucket",
        import_object_key="archive/corpus.imdi",
    )

    monkeypatch.setattr(
        "lacos.explorer.views.imdi._get_storage_service",
        lambda: _FakeImdiStorageService(),
    )

    response = client.get(
        reverse("explorer:imdi_browser", kwargs={"pk": collection.pk}),
    )

    assert response.status_code == HTTP_OK
    page = response.content.decode("utf-8")
    assert "Back to Collection" in page
    assert "Close IMDI browser" not in page
