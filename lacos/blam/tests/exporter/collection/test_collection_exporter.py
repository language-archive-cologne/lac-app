"""Tests for collection exporter."""

import pytest
from datetime import date
from xml.etree import ElementTree as ET

from lacos.blam.mappers.collection.write import CollectionExporter
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
    CollectionCreator,
    CollectionContributor,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionLicense,
    CollectionRightsHolder,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo


@pytest.fixture
def sample_collection(db):
    """Create a sample collection with all related models for testing."""
    # Create collection
    collection = Collection.objects.create(
        identifier="hdl:test/collection-001",
        source_version="1.0",
    )

    # Create header
    CollectionHeader.objects.create(
        collection=collection,
        md_creator="Test Creator",
        md_creation_date=date(2024, 1, 15),
        md_self_link="hdl:test/collection-001",
        md_profile="clarin.eu:cr1:p_test",
        md_collection_display_name="Test Collection",
    )

    # Create location
    location = CollectionLocation.objects.create(
        country_name="Germany",
        country_facet="Germany",
        country_code="DE",
    )

    # Create object language
    obj_lang = CollectionObjectLanguage.objects.create(
        display_name="English",
        name="English",
        iso_639_3_code="eng",
        glottolog_code="stan1293",
    )

    # Create general info
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="hdl:test/collection-001",
        id_type="HANDLE",
        display_title="Test Collection Title",
        description="A test collection for unit testing.",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(obj_lang)

    # Create creator
    creator = CollectionCreator.objects.create(
        family_name="Smith",
        given_name="John",
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
        rights_holder_name="Test University",
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


@pytest.mark.django_db
def test_export_produces_valid_xml(sample_collection):
    """Test that exporter produces valid XML output."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert xml_output is not None
    assert "<CMD" in xml_output
    assert 'xmlns="http://www.clarin.eu/cmd/"' in xml_output


@pytest.mark.django_db
def test_export_contains_header(sample_collection):
    """Test that exported XML contains header information."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "MdCreator" in xml_output
    assert "MdSelfLink" in xml_output
    assert "hdl:test/collection-001" in xml_output


@pytest.mark.django_db
def test_export_contains_general_info(sample_collection):
    """Test that exported XML contains general info."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "CollectionDisplayTitle" in xml_output
    assert "Test Collection Title" in xml_output
    assert "CollectionDescription" in xml_output


@pytest.mark.django_db
def test_export_contains_publication_info(sample_collection):
    """Test that exported XML contains publication info."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "CollectionPublicationYear" in xml_output
    assert "CollectionDataProvider" in xml_output
    assert "Test Provider" in xml_output


@pytest.mark.django_db
def test_export_contains_administrative_info(sample_collection):
    """Test that exported XML contains administrative info."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "AvailabilityDate" in xml_output
    assert "License" in xml_output
    assert "RightsHolder" in xml_output


@pytest.mark.django_db
def test_export_to_element_returns_element(sample_collection):
    """Test that export_to_element returns an XML Element."""
    exporter = CollectionExporter()

    element = exporter.export_to_element(sample_collection)

    assert isinstance(element, ET.Element)
    assert "CMD" in element.tag


def _find_mdlicense_element(xml_output: str) -> ET.Element:
    root = ET.fromstring(xml_output)
    for element in root.iter():
        if element.tag.split("}")[-1].lower() == "mdlicense":
            return element
    raise AssertionError("MdLicense element not found in exported XML")


@pytest.mark.django_db
def test_export_prefers_header_md_license(sample_collection):
    header = sample_collection.header.first()
    header.md_license = "CC0"
    header.md_license_uri = "https://creativecommons.org/public-domain/cc0/"
    header.save(update_fields=["md_license", "md_license_uri"])

    admin_info = sample_collection.administrative_info.first()
    license_obj = admin_info.licenses.first()
    license_obj.license_name = "Copyright"
    license_obj.license_identifier = "https://en.wikipedia.org/wiki/Copyright"
    license_obj.save(update_fields=["license_name", "license_identifier"])

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    mdlicense = _find_mdlicense_element(xml_output)

    assert (mdlicense.text or "").strip() == "CC0"
    assert (mdlicense.get("URI") or mdlicense.get("uri")) == "https://creativecommons.org/public-domain/cc0/"


@pytest.mark.django_db
def test_export_falls_back_to_administrative_license(sample_collection):
    header = sample_collection.header.first()
    header.md_license = None
    header.md_license_uri = None
    header.save(update_fields=["md_license", "md_license_uri"])

    admin_info = sample_collection.administrative_info.first()
    license_obj = admin_info.licenses.first()
    license_obj.license_name = "Copyright"
    license_obj.license_identifier = "https://en.wikipedia.org/wiki/Copyright"
    license_obj.save(update_fields=["license_name", "license_identifier"])

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    mdlicense = _find_mdlicense_element(xml_output)

    assert (mdlicense.text or "").strip() == "Copyright"
    assert (mdlicense.get("URI") or mdlicense.get("uri")) == "https://en.wikipedia.org/wiki/Copyright"


# ---------------------------------------------------------------------------
# ResourceProxyList
# ---------------------------------------------------------------------------

CMD_NS = "http://www.clarin.eu/cmd/"


def _find_resource_proxies(xml_output: str) -> list[ET.Element]:
    root = ET.fromstring(xml_output)
    return root.findall(f".//{{{CMD_NS}}}ResourceProxy")


def _find_creator_name_identifiers(xml_output: str) -> list[ET.Element]:
    root = ET.fromstring(xml_output)
    return root.findall(f".//{{{CMD_NS}}}CreatorNameIdentifier")


def _find_contributor_name_identifiers(xml_output: str) -> list[ET.Element]:
    root = ET.fromstring(xml_output)
    return root.findall(f".//{{{CMD_NS}}}ContributorNameIdentifier")


@pytest.mark.django_db
def test_export_resource_proxy_list_with_bundles(sample_collection):
    """Bundles appear as ResourceProxy entries with Metadata type."""
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-001")
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=sample_collection,
    )

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    proxies = _find_resource_proxies(xml_output)

    assert len(proxies) == 1
    proxy = proxies[0]
    assert proxy.get("id") == "rp1"

    rt = proxy.find(f"{{{CMD_NS}}}ResourceType")
    assert rt is not None
    assert rt.text.strip() == "Metadata"

    rr = proxy.find(f"{{{CMD_NS}}}ResourceRef")
    assert rr is not None
    assert rr.text.strip() == "hdl:test/bundle-001"


@pytest.mark.django_db
def test_export_resource_proxy_list_multiple_bundles(sample_collection):
    """Multiple bundles produce sequentially numbered ResourceProxy entries."""
    for i in range(3):
        bundle = Bundle.objects.create(identifier=f"hdl:test/bundle-{i:03d}")
        BundleStructuralInfo.objects.create(
            bundle=bundle, is_member_of_collection=sample_collection,
        )

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    proxies = _find_resource_proxies(xml_output)

    assert len(proxies) == 3
    ids = [p.get("id") for p in proxies]
    assert ids == ["rp1", "rp2", "rp3"]


@pytest.mark.django_db
def test_export_resource_proxy_list_empty_when_no_bundles(sample_collection):
    """ResourceProxyList should be empty when there are no bundles."""
    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    proxies = _find_resource_proxies(xml_output)

    assert len(proxies) == 0


# ---------------------------------------------------------------------------
# Keywords export
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_export_contains_keywords(sample_collection):
    """Keywords on general info should appear in exported XML."""
    general_info = sample_collection.general_info.first()
    kw1 = CollectionKeyword.objects.create(value="linguistics")
    kw2 = CollectionKeyword.objects.create(value="fieldwork")
    general_info.keywords.add(kw1, kw2)

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)

    assert "linguistics" in xml_output
    assert "fieldwork" in xml_output


@pytest.mark.django_db
def test_export_creator_identifier_type_normalizes_lowercase_value(sample_collection):
    """Lowercase legacy identifier types should still export IdentifierType."""
    creator = sample_collection.publication_info.first().creators.first()
    creator.name_identifier = "https://orcid.org/0000-0001-2345-6789"
    creator.name_identifier_type = "orcid"
    creator.save(update_fields=["name_identifier", "name_identifier_type"])

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    creator_identifiers = _find_creator_name_identifiers(xml_output)

    assert len(creator_identifiers) == 1
    assert creator_identifiers[0].get("IdentifierType") == "ORCID"


@pytest.mark.django_db
def test_export_contributor_identifier_type_normalizes_lowercase_value(sample_collection):
    """Contributor identifier types should export with uppercase schema tokens."""
    pub_info = sample_collection.publication_info.first()
    contributor = CollectionContributor.objects.create(
        family_name="Doe",
        given_name="Jane",
        contributor_display_name="Jane Doe",
        name_identifier="https://isni.org/isni/000000012146438X",
        name_identifier_type="isni",
    )
    pub_info.contributors.add(contributor)

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    contributor_identifiers = _find_contributor_name_identifiers(xml_output)

    assert len(contributor_identifiers) == 1
    assert contributor_identifiers[0].get("IdentifierType") == "ISNI"


@pytest.mark.django_db
def test_export_creator_identifier_type_defaults_to_other_for_unknown_value(sample_collection):
    """Unknown identifier types should not drop IdentifierType in XML export."""
    creator = sample_collection.publication_info.first().creators.first()
    creator.name_identifier = "https://example.com/id/creator-1"
    creator.name_identifier_type = "legacy"
    creator.save(update_fields=["name_identifier", "name_identifier_type"])

    exporter = CollectionExporter()
    xml_output = exporter.export(sample_collection)
    creator_identifiers = _find_creator_name_identifiers(xml_output)

    assert len(creator_identifiers) == 1
    assert (creator_identifiers[0].get("IdentifierType") or "").upper() == "OTHER"
