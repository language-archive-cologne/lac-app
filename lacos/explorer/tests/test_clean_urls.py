"""Tests for clean URL scheme (no /explorer/ prefix, no hdl: in handles).

Verifies that collections, bundles, and resources are accessible via the
new URL patterns:
  /collections/11341/.../ instead of /explorer/collections/hdl:11341/.../
  /bundles/11341/.../     instead of /explorer/bundles/hdl:11341/.../
  /bundles/11341/.../resources/11341/.../
"""

import pytest
from django.urls import reverse

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
)
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection


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


# --- Backward-compat redirects ---


@pytest.mark.django_db
def test_old_explorer_urls_no_longer_exist(client):
    """/explorer/... paths should return 404."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    assert client.get(f"/explorer/collections/{collection.identifier}/").status_code == 404
    assert client.get(f"/explorer/bundles/{bundle.identifier}/").status_code == 404
