import pytest
from unittest.mock import patch

from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd, BundleIdIdentifierType
from blam_schemas.bundle.blam_bundle_repository_v1_1 import (
    BundleIdIdentifierType as BundleIdIdentifierTypeV11,
)
from lacos.blam.mappers.bundle.read.import_bundle_general_info import (
    create_bundle_general_info,
    import_general_info,
    map_identifier_type,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleKeyword,
    BundleLocation,
    BundleObjectLanguage,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices


@pytest.fixture
def test_bundle():
    """Create a test bundle for testing."""
    return Bundle.objects.create(identifier="test-general-info-bundle")

@pytest.fixture
def real_bundle_xml():
    """Get the XML content from a real bundle file in the data directory."""
    import os
    xml_path = os.path.join('data', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        xml_path = os.path.join('data', 'zaghawa', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()


@pytest.fixture
def real_cmd_data(real_bundle_xml):
    """Parse real bundle XML into CMD data"""
    from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
    with patch('django.core.exceptions.ValidationError', Exception):
        return BundleImporter.validate_xml(real_bundle_xml)


@pytest.fixture
def cmd_data():
    """Create sample CMD data for testing"""
    cmd = Cmd()
    cmd.components = type('obj', (object,), {})
    cmd.components.blam_bundle_repository_v1_0 = type('obj', (object,), {})
    
    # Create bundle_general_info
    bundle_info = type('obj', (object,), {})
    bundle_info.bundle_display_title = "Bodyparts 1"
    bundle_info.bundle_description = "Translation of the Body parts in a Swadesh list from English to Zaghawa"
    bundle_info.bundle_version = "1"
    
    # Create bundle_id
    bundle_id = type('obj', (object,), {})
    bundle_id.value = "hdl:11341/00-0000-0000-0000-1AE5-2"
    bundle_id.identifier_type = "Handle"
    bundle_info.bundle_id = [bundle_id]
    
    # Create recording date
    recording_date = type('obj', (object,), {})
    recording_date.value = "2014-10-09"
    bundle_info.bundle_recording_date = recording_date
    
    # Create bundle_location
    location = type('obj', (object,), {})
    location.bundle_geo_location = "50.9282,6.92826"
    location.bundle_location_name = ""
    location.bundle_location_facet = "University Cologne"
    location.bundle_region_name = ""
    location.bundle_region_facet = "North Rhine-Westphalia"
    location.bundle_country_name = ""
    location.bundle_country_facet = "Germany"
    location.bundle_country_code = type('obj', (object,), {'value': "DE"})
    bundle_info.bundle_location = location
    
    # Add keywords
    keyword_list = type('obj', (object,), {})
    keyword_list.bundle_keyword = [
        "Elicitation", "Translation", "Swadesh list", "speech", "bodyparts",
        "interactive", "semi-spontaneous", "elicited", "Dialogue", "Face to Face"
    ]
    bundle_info.bundle_keywords = keyword_list
    
    # Add object languages
    lang = type('obj', (object,), {})
    lang.object_language_display_name = ""
    lang.object_language_name = "Beria"
    lang.object_language_iso639_3_code = type('obj', (object,), {'value': "zag"})
    lang.object_language_glottolog_code = type('obj', (object,), {'value': "zagh1240"})
    
    # Add alternative names
    alt_names = type('obj', (object,), {})
    alt_names.object_language_alternative_name = [
        "Beri", "Beri-Aa", "Berri", "Kebadi", "Kuyuk", "Merida", "Soghaua",
        "Zagaoua", "Zagawa", "Zaghawa", "Zauge", "Zeggaoua", "Zeghawa",
        "Zorhaua", "Bideyat", "Sagava (Zaghawa)", "Język zaghawa",
        "Zaghawa language", "Загава", "Загаваски јазик"
    ]
    lang.object_language_alternative_names = alt_names
    
    # Add language taxonomy
    taxonomy = type('obj', (object,), {})
    taxonomy.object_language_language_family = ["Saharan", "Eastern Saharan"]
    lang.object_language_taxonomy = taxonomy
    
    languages = type('obj', (object,), {})
    languages.bundle_object_language = [lang]
    bundle_info.bundle_object_languages = languages
    
    cmd.components.blam_bundle_repository_v1_0.bundle_general_info = bundle_info
    return cmd


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the bundle general info from CMD data
    bundle_info = real_cmd_data.components.blam_bundle_repository_v1_0.bundle_general_info
    
    # Verify basic fields
    assert bundle_info.bundle_display_title == "Bodyparts 1"
    assert bundle_info.bundle_description == "Translation of the Body parts in a Swadesh list from English to Zaghawa"
    assert bundle_info.bundle_version == "1"
    
    # Verify bundle ID
    assert bundle_info.bundle_id[0].value == "hdl:11341/00-0000-0000-0000-1AE5-2"
    assert bundle_info.bundle_id[0].identifier_type == BundleIdIdentifierType.HANDLE
    
    # Verify recording date
    assert bundle_info.bundle_recording_date.value == "2014-10-09"
    
    # Verify location
    location = bundle_info.bundle_location
    assert location.bundle_geo_location == "50.9282,6.92826"
    assert location.bundle_location_facet == "University Cologne"
    assert location.bundle_region_facet == "North Rhine-Westphalia"
    assert location.bundle_country_facet == "Germany"
    assert location.bundle_country_code.value == "DE"
    
    # Verify keywords
    keywords = bundle_info.bundle_keywords.bundle_keyword
    assert len(keywords) == 10
    assert "Elicitation" in keywords
    assert "Translation" in keywords
    assert "Swadesh list" in keywords
    assert "speech" in keywords
    assert "bodyparts" in keywords
    assert "interactive" in keywords
    assert "semi-spontaneous" in keywords
    assert "elicited" in keywords
    assert "Dialogue" in keywords
    assert "Face to Face" in keywords
    
    # Verify languages
    languages = bundle_info.bundle_object_languages.bundle_object_language
    assert len(languages) == 1
    lang = languages[0]
    assert lang.object_language_name == "Beria"
    assert lang.object_language_iso639_3_code.value == "zag"
    assert lang.object_language_glottolog_code.value == "zagh1240"
    
    # Verify alternative names
    alt_names = lang.object_language_alternative_names.object_language_alternative_name
    assert len(alt_names) == 20  # Updated to match actual XML data
    assert "Beri" in alt_names
    assert "Beri-Aa" in alt_names
    assert "Berri" in alt_names
    assert "Kebadi" in alt_names
    assert "Kuyuk" in alt_names
    assert "Merida" in alt_names
    assert "Soghaua" in alt_names
    assert "Zagaoua" in alt_names
    assert "Zagawa" in alt_names
    assert "Zaghawa" in alt_names
    assert "Zauge" in alt_names
    assert "Zeggaoua" in alt_names
    assert "Zeghawa" in alt_names
    assert "Zorhaua" in alt_names
    assert "Bideyat" in alt_names
    assert "Sagava (Zaghawa)" in alt_names
    assert "Język zaghawa" in alt_names
    assert "Zaghawa language" in alt_names
    assert "Загава" in alt_names
    assert "Загаваски јазик" in alt_names
    
    # Verify language taxonomy
    taxonomy = lang.object_language_taxonomy
    assert taxonomy.object_language_language_family == ["Saharan", "Eastern Saharan"]


@pytest.mark.django_db
def test_general_info_data_mapping(real_cmd_data, test_bundle):
    """Test that general info is mapped correctly from CMD to Django model"""
    # Test import with real data
    general_info = import_general_info(real_cmd_data, test_bundle)
    
    # Verify the object was created and fields were set correctly
    assert isinstance(general_info, BundleGeneralInfo)
    assert general_info.display_title == "Bodyparts 1"
    assert general_info.description == "Translation of the Body parts in a Swadesh list from English to Zaghawa"
    assert general_info.version == "1"
    assert general_info.id_value == "hdl:11341/00-0000-0000-0000-1AE5-2"
    assert general_info.id_type == "HANDLE"
    
    # Verify the association with the bundle
    assert test_bundle.general_info.count() == 1
    assert test_bundle.general_info.first() == general_info
    
    # Check location was created and linked
    assert general_info.location is not None
    assert isinstance(general_info.location, BundleLocation)
    assert general_info.location.geo_location == "50.9282,6.92826"
    assert general_info.location.location_facet == "University Cologne"
    assert general_info.location.region_facet == "North Rhine-Westphalia"
    assert general_info.location.country_facet == "Germany"
    assert general_info.location.country_code == "DE"
    
    # Verify keywords were imported
    assert general_info.keywords.count() == 10
    keywords = list(general_info.keywords.all().values_list('value', flat=True))
    assert "Elicitation" in keywords
    assert "Translation" in keywords
    assert "Swadesh list" in keywords
    
    # Verify languages were imported and linked via ManyToMany
    assert general_info.object_languages.count() == 1
    # Get the canonical language object via the M2M relationship
    language = general_info.object_languages.first()
    assert language is not None # Ensure the relationship worked
    assert language.name == "Beria"
    assert language.iso_639_3_code == "zag"
    assert language.glottolog_code == "zagh1240"
    
    # Verify alternative names (now linked to the canonical language object)
    alt_names = list(language.alternative_names.all().values_list('value', flat=True))
    assert "Beri" in alt_names
    assert "Zaghawa" in alt_names
    assert "Zaghawa language" in alt_names
    
    # Verify language taxonomy (linked via the canonical language object)
    # Assuming the related name on the OneToOneField is 'bundle_object_language_taxonomy'
    taxonomy = language.bundle_object_language_taxonomy 
    assert taxonomy is not None
    families = list(taxonomy.language_family.all().values_list('value', flat=True))
    assert "Saharan" in families
    assert "Eastern Saharan" in families


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data, test_bundle):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    general_info1 = import_general_info(real_cmd_data, test_bundle)
    
    # Second import with same ID should get existing record
    general_info2 = import_general_info(real_cmd_data, test_bundle)
    
    # Should be the same record
    assert general_info1.pk == general_info2.pk
    
    # Count should still be 1
    count = BundleGeneralInfo.objects.filter(id_value="hdl:11341/00-0000-0000-0000-1AE5-2").count()
    assert count == 1
    # Add check for canonical language count
    assert BundleObjectLanguage.objects.count() == 1 # Only one 'zag' language should exist


def test_map_identifier_type_handles_v10_enum():
    assert map_identifier_type(BundleIdIdentifierType.HANDLE) == IdentifierTypeChoices.HANDLE.value
    assert map_identifier_type(BundleIdIdentifierType.DOI) == IdentifierTypeChoices.DOI.value


def test_map_identifier_type_handles_v11_enum():
    assert map_identifier_type(BundleIdIdentifierTypeV11.HANDLE) == IdentifierTypeChoices.HANDLE.value
    assert map_identifier_type(BundleIdIdentifierTypeV11.URN) == IdentifierTypeChoices.URN.value


def test_map_identifier_type_handles_strings():
    assert map_identifier_type("Handle") == IdentifierTypeChoices.HANDLE.value
    assert map_identifier_type("URN") == IdentifierTypeChoices.URN.value
    assert map_identifier_type("unknown") == IdentifierTypeChoices.DOI.value


@pytest.mark.django_db
def test_create_bundle_general_info_updates_existing_wrong_id_type(test_bundle):
    location = BundleLocation.objects.create(
        region_name="NRW",
        country_name="Germany",
        country_code="DE",
    )
    existing = BundleGeneralInfo.objects.create(
        id_value="hdl:11341/0000-0000-0000-3DC4",
        id_type=IdentifierTypeChoices.DOI.value,
        display_title="old",
        description="old",
        version="1",
        location=location,
        bundle=test_bundle,
    )

    bundle_id = type("obj", (), {"value": existing.id_value, "identifier_type": "Handle"})
    recording_date = type("obj", (), {"value": "2014-10-09"})
    bundle_info = type(
        "obj",
        (),
        {
            "bundle_id": [bundle_id],
            "bundle_display_title": "new title",
            "bundle_description": "new description",
            "bundle_version": "2",
            "bundle_recording_date": recording_date,
        },
    )

    updated = create_bundle_general_info(bundle_info, location, test_bundle)
    assert updated.pk == existing.pk
    assert updated.id_type == IdentifierTypeChoices.HANDLE.value
    assert BundleGeneralInfo.objects.filter(id_value=existing.id_value).count() == 1


@pytest.mark.django_db
def test_language_update_behavior(real_cmd_data, test_bundle):
    """Test that re-importing updates existing language data based on ISO code."""
    # First import
    import_general_info(real_cmd_data, test_bundle)
    assert BundleObjectLanguage.objects.count() == 1
    lang1 = BundleObjectLanguage.objects.get(iso_639_3_code='zag')
    assert lang1.name == "Beria" 
    assert lang1.glottolog_code == "zagh1240"

    # Modify the name in the source data for the second import
    # IMPORTANT: Modify the actual cmd_data fixture used by the importer
    bundle_info_schema = real_cmd_data.components.blam_bundle_repository_v1_0.bundle_general_info
    bundle_info_schema.bundle_object_languages.bundle_object_language[0].object_language_name = "Zaghawa_Updated"
    bundle_info_schema.bundle_object_languages.bundle_object_language[0].object_language_glottolog_code.value = "xxxx1111"

    # Second import (using the modified cmd_data)
    import_general_info(real_cmd_data, test_bundle)
    
    # Count should still be 1 (no new language created)
    assert BundleObjectLanguage.objects.count() == 1
    
    # Verify the existing object was updated
    lang2 = BundleObjectLanguage.objects.get(iso_639_3_code='zag')
    assert lang1.pk == lang2.pk # Should be the same object
    assert lang2.name == "Zaghawa_Updated" # Name should be updated
    assert lang2.glottolog_code == "xxxx1111" # Glottolog code should be updated 
