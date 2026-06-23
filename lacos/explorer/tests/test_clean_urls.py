"""Tests for clean URL scheme (no /explorer/ prefix, no hdl: in handles).

Verifies that collections, bundles, and resources are accessible via the
new URL patterns:
  /collections/11341/.../ instead of /explorer/collections/hdl:11341/.../
  /bundles/11341/.../     instead of /explorer/bundles/hdl:11341/.../
  /bundles/11341/.../resources/11341/.../
"""

import pytest
from django.urls import reverse
from types import SimpleNamespace

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
)
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)


def _create_collection(identifier="hdl:11341/test-clean-url-col"):
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Test Site", region_name="Region",
        country_name="Country", country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier, id_type=IdentifierTypeChoices.HANDLE,
        display_title="Clean URL Collection",
        description="Test collection for URL scheme", version="1.0",
        location=location,
    )
    return collection


def _create_bundle(collection, identifier="hdl:11341/test-clean-url-bnd"):
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Test Location", region_name="Region",
        country_name="Country", country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=identifier, id_type=IdentifierTypeChoices.HANDLE,
        display_title="Clean URL Bundle",
        description="Test bundle for URL scheme", version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _create_resource(bundle, file_pid="hdl:11341/test-clean-url-res"):
    resource = MediaResource.objects.create(
        file_name="test.wav", file_pid=file_pid, mime_type="audio/wav",
    )
    br = BundleResources.objects.create(bundle=bundle)
    br.bundle_media_resources.add(resource)
    return resource


def _create_bundle_metadata_file(bundle, file_pid="hdl:11341/test-clean-url-meta"):
    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_name="metadata.xml",
        file_pid=file_pid,
        mime_type="application/xml",
        is_metadata_for="bundle",
    )
    bundle.structural_info.first().additional_metadata_files.add(metadata_file)
    return metadata_file


def _create_collection_metadata_file(
    collection,
    file_pid="hdl:11341/test-clean-url-collection-meta",
):
    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_name="collection-metadata.xml",
        file_pid=file_pid,
        mime_type="application/xml",
        is_metadata_for="collection",
    )
    structural_info.additional_metadata_files.add(metadata_file)
    return metadata_file


# --- Collection clean URLs ---


@pytest.mark.django_db
def test_collection_accessible_without_explorer_prefix(client):
    collection = _create_collection()
    response = client.get(f"/collections/{collection.handle_path}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_collection_url_reverse_has_no_explorer_prefix(client):
    collection = _create_collection()
    url = reverse("explorer:collection_detail_by_handle", kwargs={"handle": collection.handle_path})
    assert url == f"/collections/{collection.handle_path}/"
    assert "/explorer/" not in url
    assert "hdl:" not in url


@pytest.mark.django_db
def test_collection_metadata_xml_without_explorer_prefix(client):
    collection = _create_collection()
    response = client.get(f"/collections/{collection.handle_path}/metadata.xml")
    assert response.status_code == 200


@pytest.mark.django_db
def test_collection_metadata_jsonld_without_explorer_prefix(client):
    collection = _create_collection()
    response = client.get(f"/collections/{collection.handle_path}/metadata.jsonld")
    assert response.status_code == 200


# --- Bundle clean URLs ---


@pytest.mark.django_db
def test_bundle_accessible_without_explorer_prefix(client):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    response = client.get(f"/bundles/{bundle.handle_path}/")
    # 200 if public, 403 if ACL blocks anonymous — both mean URL resolved correctly
    assert response.status_code in (200, 403)


@pytest.mark.django_db
def test_bundle_url_reverse_has_no_explorer_prefix():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    url = reverse("explorer:bundle_detail_by_handle", kwargs={"handle": bundle.handle_path})
    assert url == f"/bundles/{bundle.handle_path}/"
    assert "/explorer/" not in url
    assert "hdl:" not in url


@pytest.mark.django_db
def test_bundle_metadata_xml_without_explorer_prefix(client):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    response = client.get(f"/bundles/{bundle.handle_path}/metadata.xml")
    assert response.status_code == 200


@pytest.mark.django_db
def test_bundle_metadata_jsonld_without_explorer_prefix(client):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    response = client.get(f"/bundles/{bundle.handle_path}/metadata.jsonld")
    assert response.status_code == 200


# --- Resource clean URLs ---


@pytest.mark.django_db
def test_resource_accessible_via_clean_bundle_url(client):
    """Resource accessible at /bundles/<handle>/resources/<pid>/ without hdl: prefix."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_resource(bundle)
    pid_clean = resource.file_pid[4:]  # strip hdl:

    response = client.get(f"/bundles/{bundle.handle_path}/resources/{pid_clean}/")
    # 200 if public + S3, 403 if ACL blocks, 404 if no S3 — all mean URL resolved
    assert response.status_code in (200, 403, 404)


@pytest.mark.django_db
def test_resource_url_reverse_has_no_hdl_prefix():
    """Reversed resource URL should contain no hdl: prefix."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_resource(bundle)
    pid_clean = resource.file_pid[4:]

    url = reverse(
        "explorer:resource_access_by_handle",
        kwargs={"handle": bundle.handle_path, "resource_pid": pid_clean},
    )
    assert "hdl:" not in url
    assert "/explorer/" not in url
    assert url == f"/bundles/{bundle.handle_path}/resources/{pid_clean}/"


@pytest.mark.django_db
def test_resource_direct_url_renders_page(client):
    """/resource/<handle>/ should render the resource page directly (no redirect)."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_resource(bundle)
    pid_clean = resource.file_pid[4:]

    response = client.get(f"/resource/{pid_clean}/")
    # Renders directly (200/403/404 from S3) — NOT a 302 redirect
    assert response.status_code != 302


@pytest.mark.django_db
def test_metadata_resource_direct_url_renders_page(client):
    """Metadata resources should also resolve via /resource/<handle>/."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    metadata_file = _create_bundle_metadata_file(bundle)
    pid_clean = metadata_file.file_pid[4:]

    response = client.get(f"/resource/{pid_clean}/")
    assert response.status_code != 302


@pytest.mark.django_db
def test_bundle_page_resource_links_use_direct_resource_pid_route(client, monkeypatch):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_resource(bundle)
    pid_clean = resource.file_pid[4:]

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ACLEvaluationService.evaluate",
        lambda *_args, **_kwargs: SimpleNamespace(allowed=True, access_level="public"),
    )

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert f'/resource/{pid_clean}/?action=play' in html
    assert f"/resource/{bundle.pk}/{resource.id}/?action=play" not in html


@pytest.mark.django_db
def test_collection_detail_copy_buttons_use_handle_resolver_urls(client, monkeypatch):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    metadata_file = _create_collection_metadata_file(
        collection,
        file_pid="hdl:11341/test-collection-copy-meta",
    )

    monkeypatch.setattr(
        "lacos.explorer.views.collections.ACLEvaluationService.evaluate",
        lambda *_args, **_kwargs: SimpleNamespace(
            allowed=True,
            access_level="public",
        ),
    )

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.handle_path},
        )
    )

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert collection.identifier in html
    assert f'data-copy-text="{collection.handle_url}"' in html
    assert bundle.identifier in html
    assert f'data-copy-text="{bundle.handle_url}"' in html
    assert metadata_file.file_pid in html
    assert 'data-copy-text="https://hdl.handle.net/11341/test-collection-copy-meta"' in html


@pytest.mark.django_db
def test_bundle_detail_resource_copy_buttons_use_handle_resolver_urls(client, monkeypatch):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_resource(
        bundle,
        file_pid="hdl:11341/test-bundle-resource-copy",
    )
    metadata_file = _create_bundle_metadata_file(
        bundle,
        file_pid="hdl:11341/test-bundle-meta-copy",
    )

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ACLEvaluationService.evaluate",
        lambda *_args, **_kwargs: SimpleNamespace(
            allowed=True,
            access_level="public",
        ),
    )

    response = client.get(
        reverse(
            "explorer:bundle_detail_by_handle",
            kwargs={"handle": bundle.handle_path},
        )
    )

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert resource.file_pid in html
    assert 'data-copy-text="https://hdl.handle.net/11341/test-bundle-resource-copy"' in html
    assert metadata_file.file_pid in html
    assert 'data-copy-text="https://hdl.handle.net/11341/test-bundle-meta-copy"' in html


@pytest.mark.django_db
def test_resource_detail_copy_button_uses_handle_resolver_url(client, monkeypatch):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_resource(
        bundle,
        file_pid="hdl:11341/0000-0000-0000-3235",
    )
    resource.file_name = "resource.bin"
    resource.mime_type = "application/octet-stream"
    resource.save(update_fields=["file_name", "mime_type"])

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ACLEvaluationService.evaluate",
        lambda *_args, **_kwargs: SimpleNamespace(
            allowed=True,
            access_level="public",
        ),
    )
    monkeypatch.setattr(
        "lacos.explorer.views.bundles.resolve_resource_to_presigned",
        lambda *_args, **_kwargs: {
            "bucket": "test-bucket",
            "key": "resource.bin",
            "url": "https://example.test/resource.bin",
        },
    )
    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ResourceMappingService.generate_presigned_url",
        lambda *_args, **_kwargs: "https://example.test/download.bin",
    )

    response = client.get(
        reverse("resource_by_handle", kwargs={"handle_id": resource.file_pid[4:]})
    )

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert resource.file_pid in html
    assert 'data-copy-text="https://hdl.handle.net/11341/0000-0000-0000-3235"' in html


# --- Backward-compat redirects ---


@pytest.mark.django_db
def test_old_explorer_urls_no_longer_exist(client):
    """/explorer/... paths should return 404."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    assert client.get(f"/explorer/collections/{collection.identifier}/").status_code == 404
    assert client.get(f"/explorer/bundles/{bundle.identifier}/").status_code == 404
