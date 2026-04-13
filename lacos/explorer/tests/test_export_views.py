"""Regression tests for XML/JSON-LD export views.

Verifies that export views handle bundles and collections with and without
optional related data (publication info, admin info) without crashing.
"""

from __future__ import annotations

import pytest
from django.test import Client

from lacos.blam.models import Bundle, Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleLocation,
    BundleObjectLanguage,
)
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_publication_info import (
    BundleCreator,
    BundlePublicationInfo,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_publication_info import (
    CollectionCreator,
    CollectionPublicationInfo,
)


def _create_bundle(*, with_publication=True):
    """Create a bundle with configurable optional data."""
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-001")

    BundleHeader.objects.create(
        bundle=bundle,
        md_creator="Test",
        md_self_link="https://example.com/bundle-001",
        md_profile="https://example.com/profile",
    )

    location = BundleLocation.objects.create(
        region_name="Europe",
        country_name="Germany",
        country_code="DE",
        region_facet="Europe",
        country_facet="Germany",
    )

    language = BundleObjectLanguage.objects.create(
        display_name="German",
        name="German",
        iso_639_3_code="deu",
        glottolog_code="stan1295",
    )

    general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value="BID-001",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Test Bundle",
        description="A test bundle",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(language)

    if with_publication:
        pub_info = BundlePublicationInfo.objects.create(
            bundle=bundle,
            publication_year=2024,
            data_provider="LAC",
            identifier="BID-001",
            identifier_type="HANDLE",
        )
        creator = BundleCreator.objects.create(family_name="Doe")
        pub_info.creators.add(creator)

    return bundle


def _create_collection(*, with_publication=True):
    """Create a collection with configurable optional data."""
    collection = Collection.objects.create(identifier="hdl:test/collection-001")

    CollectionHeader.objects.create(
        collection=collection,
        md_creator="Test",
        md_self_link="https://example.com/collection-001",
        md_profile="https://example.com/profile",
    )

    location = CollectionLocation.objects.create(
        region_name="Europe",
        country_name="Germany",
        country_code="DE",
        region_facet="Europe",
        country_facet="Germany",
    )

    language = CollectionObjectLanguage.objects.create(
        display_name="German",
        name="German",
        iso_639_3_code="deu",
        glottolog_code="stan1295",
    )

    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-001",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Test Collection",
        description="A test collection",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(language)

    if with_publication:
        pub_info = CollectionPublicationInfo.objects.create(
            collection=collection,
            publication_year=2024,
            data_provider="LAC",
        )
        creator = CollectionCreator.objects.create(family_name="Doe")
        pub_info.creators.add(creator)

    return collection


# --- Bundle XML export tests ---


@pytest.mark.django_db
def test_bundle_xml_export_success():
    """Bundle with full data exports as valid XML."""
    bundle = _create_bundle()
    client = Client()
    response = client.get(f"/bundles/{bundle.identifier}/metadata.xml")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/xml"
    assert b"<" in response.content


@pytest.mark.django_db
def test_bundle_xml_export_without_publication():
    """Bundle without publication info should export successfully."""
    bundle = _create_bundle(with_publication=False)
    client = Client()
    response = client.get(f"/bundles/{bundle.identifier}/metadata.xml")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/xml"


@pytest.mark.django_db
def test_bundle_xml_htmx_returns_html():
    """HTMX request to bundle XML view returns HTML partial."""
    bundle = _create_bundle()
    client = Client()
    response = client.get(
        f"/bundles/{bundle.identifier}/metadata.xml",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"metadata-content" in response.content


@pytest.mark.django_db
def test_bundle_jsonld_htmx_returns_html():
    """HTMX request to bundle JSON-LD view returns HTML partial."""
    bundle = _create_bundle()
    client = Client()
    response = client.get(
        f"/bundles/{bundle.identifier}/metadata.jsonld",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"metadata-content" in response.content


# --- Collection XML export tests ---


@pytest.mark.django_db
def test_collection_xml_export_success():
    """Collection with full data exports as valid XML."""
    collection = _create_collection()
    client = Client()
    response = client.get(
        f"/collections/{collection.identifier}/metadata.xml"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/xml"
    assert b"<" in response.content


@pytest.mark.django_db
def test_collection_xml_export_without_publication():
    """Collection without publication info should export successfully."""
    collection = _create_collection(with_publication=False)
    client = Client()
    response = client.get(
        f"/collections/{collection.identifier}/metadata.xml"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/xml"


@pytest.mark.django_db
def test_collection_xml_htmx_returns_html():
    """HTMX request to collection XML view returns HTML partial."""
    collection = _create_collection()
    client = Client()
    response = client.get(
        f"/collections/{collection.identifier}/metadata.xml",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"metadata-content" in response.content


@pytest.mark.django_db
def test_collection_jsonld_htmx_returns_html():
    """HTMX request to collection JSON-LD view returns HTML partial."""
    collection = _create_collection()
    client = Client()
    response = client.get(
        f"/collections/{collection.identifier}/metadata.jsonld",
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"metadata-content" in response.content
