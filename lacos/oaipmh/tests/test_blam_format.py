"""Tests for OAI-PMH BLAM metadata format."""

import pytest
from datetime import date
from django.urls import reverse

from lacos.oaipmh.formats.blam import BLAMSerializer
from lacos.oaipmh.identifiers import build_oai_identifier
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleLocation,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
    CollectionCreator,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionLicense,
    CollectionRightsHolder,
)


@pytest.fixture
def sample_collection(db):
    """Create a sample collection with all related models for testing."""
    # Create collection
    collection = Collection.objects.create(
        identifier="hdl:test/blam-oai-001",
        source_version="1.0",
    )

    # Create header
    CollectionHeader.objects.create(
        collection=collection,
        md_creator="Test Creator",
        md_creation_date=date(2024, 1, 15),
        md_self_link="hdl:test/blam-oai-001",
        md_profile="clarin.eu:cr1:p_test",
        md_collection_display_name="BLAM OAI Test",
    )

    # Create location
    location = CollectionLocation.objects.create(
        country_name="Germany",
        country_facet="Germany",
        country_code="DE",
    )

    # Create object language
    obj_lang = CollectionObjectLanguage.objects.create(
        display_name="German",
        name="German",
        iso_639_3_code="deu",
        glottolog_code="stan1295",
    )

    # Create general info
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="hdl:test/blam-oai-001",
        id_type="HANDLE",
        display_title="BLAM OAI Test Collection",
        description="Testing BLAM format in OAI-PMH.",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(obj_lang)

    # Create creator
    creator = CollectionCreator.objects.create(
        family_name="Müller",
        given_name="Hans",
    )

    # Create publication info
    pub_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="Test Provider",
    )
    pub_info.creators.add(creator)

    # Create license
    license_obj = CollectionLicense.objects.create(
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        access="open",
    )

    # Create rights holder
    rights_holder = CollectionRightsHolder.objects.create(
        rights_holder_name="Test Institution",
    )

    # Create administrative info
    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=collection,
        access_level="public",
        availability_date=date(2024, 1, 15),
    )
    admin_info.licenses.add(license_obj)
    admin_info.rights_holders.add(rights_holder)

    return collection


@pytest.fixture
def sample_bundle(db):
    """Create a sample bundle with the minimum metadata needed for BLAM export."""
    bundle = Bundle.objects.create(identifier="hdl:test/blam-oai-bundle-001")
    location = BundleLocation.objects.create(
        country_name="Germany",
        country_facet="Germany",
        country_code="DE",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=bundle.identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="BLAM OAI Test Bundle",
        description="Testing BLAM bundle format in OAI-PMH.",
        version="1.0",
        location=location,
    )
    return bundle


@pytest.mark.django_db
def test_blam_format_in_list_metadata_formats(client):
    """Test that BLAM appears in ListMetadataFormats response."""
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "ListMetadataFormats"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "blam" in body
    assert "clarin.eu" in body


@pytest.mark.django_db
def test_blam_serializer_with_valid_collection(sample_collection):
    """Test BLAM serializer produces valid XML for a collection."""
    serializer = BLAMSerializer()

    record = {"CollectionID": sample_collection.identifier}
    xml_str = serializer.serialize(record)

    assert xml_str is not None
    assert isinstance(xml_str, str)
    assert "<CMD" in xml_str
    assert 'xmlns="http://www.clarin.eu/cmd/"' in xml_str


@pytest.mark.django_db
def test_blam_serializer_with_missing_collection():
    """Test BLAM serializer handles missing collection gracefully."""
    serializer = BLAMSerializer()

    record = {"CollectionID": "nonexistent-collection-id"}
    xml_str = serializer.serialize(record)

    assert xml_str is not None
    assert "<CMD" in xml_str


@pytest.mark.django_db
def test_blam_serializer_with_empty_record():
    """Test BLAM serializer handles empty record gracefully."""
    serializer = BLAMSerializer()

    record = {}
    xml_str = serializer.serialize(record)

    assert xml_str is not None
    assert "<CMD" in xml_str


@pytest.mark.django_db
def test_list_records_with_blam_format(client, sample_collection):
    """Test ListRecords with BLAM metadataPrefix returns collection."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "blam"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")

    # Should contain BLAM XML structure
    assert "CMD" in body or "record" in body


@pytest.mark.django_db
def test_list_records_with_blam_format_without_set_returns_collection_and_bundle(
    client,
    sample_collection,
    sample_bundle,
):
    """Test default ListRecords with BLAM returns collections and bundles."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "blam"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert f"<identifier>{build_oai_identifier(sample_collection.identifier)}</identifier>" in body
    assert f"<identifier>{build_oai_identifier(sample_bundle.identifier)}</identifier>" in body
    assert "BLAM-collection-repository_v1.2" in body
    assert "BLAM-bundle-repository_v1.1" in body


@pytest.mark.django_db
def test_get_record_with_blam_format(client, sample_collection):
    """Test GetRecord with BLAM metadataPrefix returns one collection."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "blam",
            "identifier": build_oai_identifier(sample_collection.identifier),
        },
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<GetRecord>" in body
    assert f"<identifier>{build_oai_identifier(sample_collection.identifier)}</identifier>" in body
    assert "CMD" in body


# ---------------------------------------------------------------------------
# ResourceProxyList over OAI-PMH (issues #144/#145: VLO requires >= 1 proxy)
# ---------------------------------------------------------------------------

def _resource_proxies(body: str) -> list[tuple[str, str]]:
    """Return [(ResourceType, ResourceRef)] for every ResourceProxy, ns-agnostic."""
    from xml.etree import ElementTree as ET

    def _ln(tag):
        return tag.rsplit("}", 1)[-1]

    out = []
    for el in ET.fromstring(body).iter():
        if _ln(el.tag) == "ResourceProxy":
            rt = ref = None
            for ch in el:
                if _ln(ch.tag) == "ResourceType":
                    rt = (ch.text or "").strip()
                elif _ln(ch.tag) == "ResourceRef":
                    ref = (ch.text or "").strip()
            out.append((rt, ref))
    return out


@pytest.mark.django_db
def test_get_record_collection_without_bundles_has_landing_page_proxy(
    client,
    sample_collection,
):
    """A harvested collection with no member bundles must still expose a proxy."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "blam",
            "identifier": build_oai_identifier(sample_collection.identifier),
        },
    )
    assert response.status_code == 200
    proxies = _resource_proxies(response.content.decode("utf-8"))

    assert proxies, "OAI collection record must expose at least one ResourceProxy"
    assert ("LandingPage", sample_collection.identifier) in proxies


@pytest.mark.django_db
def test_list_records_collections_set_has_no_empty_resource_proxy_lists(
    client,
    sample_collection,
    sample_bundle,
):
    """Every record in the collections set must contain a ResourceProxy."""
    from xml.etree import ElementTree as ET

    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "blam", "set": "collections"},
    )
    assert response.status_code == 200

    root = ET.fromstring(response.content.decode("utf-8"))
    records = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "record"]
    assert records, "expected at least one collection record"
    for record in records:
        proxies = [
            el for el in record.iter()
            if el.tag.rsplit("}", 1)[-1] == "ResourceProxy"
        ]
        assert proxies, "collection record with empty ResourceProxyList"


@pytest.mark.django_db
def test_get_record_bundle_without_files_has_landing_page_proxy(
    client,
    sample_bundle,
):
    """A harvested bundle with no files must still expose a proxy (issue #145)."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "blam",
            "identifier": build_oai_identifier(sample_bundle.identifier),
        },
    )
    assert response.status_code == 200
    proxies = _resource_proxies(response.content.decode("utf-8"))

    assert proxies, "OAI bundle record must expose at least one ResourceProxy"
    assert ("LandingPage", sample_bundle.identifier) in proxies


@pytest.mark.django_db
def test_unsupported_metadata_prefix_error(client):
    """Test that unsupported prefix returns proper error."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "unsupported_format"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "cannotDisseminateFormat" in body
