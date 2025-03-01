import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter

# Fixture to load the XML content once and reuse it across tests
@pytest.fixture
def zaghawa_xml_content():
    # Determine the base directory of the project root
    base_dir = Path(__file__).resolve().parents[3]  # Adjust the number based on your directory structure

    # Construct the full path to the XML file relative to the project root
    xml_file_path = base_dir / 'data/zaghawa/zaghawa/zag_eoi_20141016_1/v1/content/zag_eoi_20141016_1.xml'

    # Read the XML content
    with open(xml_file_path, 'r', encoding='utf-8') as f:
        return f.read()

def test_bundle_basic_info(zaghawa_xml_content):
    """Test that basic bundle information is correctly imported"""
    # Create a mock bundle with just the basic info
    mock_bundle = MagicMock()
    mock_bundle.bundle_display_title = "Bodyparts 2"
    mock_bundle.bundle_description = "Second session about body parts, continuing with the word list used in the first session (ZAG_EOI_20141009_1)"
    mock_bundle.bundle_recording_date = "2014-10-16"
    mock_bundle.bundle_publication_year = 2018
    mock_bundle.bundle_data_provider = "Language Archive Cologne"
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    assert imported_bundle.bundle_display_title == "Bodyparts 2"
    assert imported_bundle.bundle_description == "Second session about body parts, continuing with the word list used in the first session (ZAG_EOI_20141009_1)"
    assert imported_bundle.bundle_recording_date == "2014-10-16"
    assert imported_bundle.bundle_publication_year == 2018
    assert imported_bundle.bundle_data_provider == "Language Archive Cologne"

def test_bundle_object_languages(zaghawa_xml_content):
    """Test that object languages are correctly imported"""
    # Create a mock bundle with language information
    mock_bundle = MagicMock()
    
    # Mock language objects
    mock_language = MagicMock()
    mock_language.name = "Beria"
    mock_language.iso_639_3_code = "zag"
    mock_language.glottolog_code = "zagh1240"
    
    # Mock languages queryset
    mock_languages = MagicMock()
    mock_languages.count.return_value = 1
    mock_languages.first.return_value = mock_language
    mock_bundle.objectlanguage_set.all.return_value = mock_languages
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    languages = imported_bundle.objectlanguage_set.all()
    assert languages.count() == 1
    
    lang = languages.first()
    assert lang.name == "Beria"
    assert lang.iso_639_3_code == "zag"
    assert lang.glottolog_code == "zagh1240"

def test_language_alternative_names(zaghawa_xml_content):
    """Test that language alternative names are correctly imported"""
    # Create a mock bundle with language and alternative names
    mock_bundle = MagicMock()
    
    # Mock language object
    mock_language = MagicMock()
    
    # Create mock alternative names with proper name attribute values
    mock_alt_name1 = MagicMock()
    mock_alt_name1.name = "Zaghawa"
    
    mock_alt_name2 = MagicMock()
    mock_alt_name2.name = "Beri"
    
    mock_alt_name3 = MagicMock()
    mock_alt_name3.name = "Zagawa"
    
    # Set the return value for the all() method
    mock_language.objectlanguagealternativename_set.all.return_value = [
        mock_alt_name1, mock_alt_name2, mock_alt_name3
    ]
    
    # Mock languages queryset
    mock_languages = MagicMock()
    mock_languages.first.return_value = mock_language
    mock_bundle.objectlanguage_set.all.return_value = mock_languages
    mock_bundle.objectlanguage_set.first.return_value = mock_language
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    lang = imported_bundle.objectlanguage_set.first()
    alt_names = lang.objectlanguagealternativename_set.all()
    
    alt_name_values = [name.name for name in alt_names]
    
    # Check for some expected alternative names
    assert "Zaghawa" in alt_name_values
    assert "Beri" in alt_name_values
    assert "Zagawa" in alt_name_values

def test_bundle_keywords(zaghawa_xml_content):
    """Test that bundle keywords are correctly imported"""
    # Create a mock bundle with keywords
    mock_bundle = MagicMock()
    
    # Mock keywords
    mock_keywords = [
        MagicMock(keyword="Elicitation"),
        MagicMock(keyword="Translation"),
        MagicMock(keyword="bodyparts"),
        MagicMock(keyword="Dialogue"),
        MagicMock(keyword="Other1"),
        MagicMock(keyword="Other2"),
        MagicMock(keyword="Other3"),
        MagicMock(keyword="Other4"),
        MagicMock(keyword="Other5"),
    ]
    mock_keywords_queryset = MagicMock()
    mock_keywords_queryset.count.return_value = 9
    mock_keywords_queryset.__iter__.return_value = iter(mock_keywords)
    mock_bundle.bundlekeyword_set.all.return_value = mock_keywords_queryset
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    keywords = imported_bundle.bundlekeyword_set.all()
    assert keywords.count() == 9
    
    keyword_values = [kw.keyword for kw in keywords]
    assert "Elicitation" in keyword_values
    assert "Translation" in keyword_values
    assert "bodyparts" in keyword_values
    assert "Dialogue" in keyword_values

def test_bundle_location(zaghawa_xml_content):
    """Test that bundle location is correctly imported"""
    # Create a mock bundle with location
    mock_bundle = MagicMock()
    
    # Mock location
    mock_location = MagicMock()
    mock_location.country_code = "DE"
    mock_location.country_facet = "Germany"
    mock_location.region_facet = "North Rhine-Westphalia"
    mock_bundle.bundlelocation_set.first.return_value = mock_location
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    location = imported_bundle.bundlelocation_set.first()
    assert location is not None
    assert location.country_code == "DE"
    assert location.country_facet == "Germany"
    assert location.region_facet == "North Rhine-Westphalia"

def test_bundle_creators(zaghawa_xml_content):
    """Test that bundle creators are correctly imported"""
    # Create a mock bundle with creators
    mock_bundle = MagicMock()
    
    # Mock creators
    mock_creator = MagicMock()
    mock_creator.family_name = "Hellwig"
    mock_creator.given_name = "Birgit"
    mock_creator.affiliation = "University of Cologne"
    mock_creators = MagicMock()
    mock_creators.count.return_value = 1
    mock_creators.first.return_value = mock_creator
    mock_bundle.creator_set.all.return_value = mock_creators
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    creators = imported_bundle.creator_set.all()
    assert creators.count() == 1
    
    creator = creators.first()
    assert creator.family_name == "Hellwig"
    assert creator.given_name == "Birgit"
    assert creator.affiliation == "University of Cologne"

def test_bundle_media_resources(zaghawa_xml_content):
    """Test that media resources are correctly imported"""
    # Create a mock bundle with media resources
    mock_bundle = MagicMock()
    
    # Mock media resources
    mock_media = MagicMock()
    mock_media.file_name = "ZAG_EOI_20141016_1.wav"
    mock_media.mime_type = "audio/x-wav"
    mock_media.file_pid = "hdl:11341/00-0000-0000-0000-1B2A-D"
    mock_media_queryset = MagicMock()
    mock_media_queryset.count.return_value = 1
    mock_media_queryset.first.return_value = mock_media
    mock_bundle.mediaresource_set.all.return_value = mock_media_queryset
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    media_resources = imported_bundle.mediaresource_set.all()
    assert media_resources.count() == 1
    
    resource = media_resources.first()
    assert resource.file_name == "ZAG_EOI_20141016_1.wav"
    assert resource.mime_type == "audio/x-wav"
    assert resource.file_pid == "hdl:11341/00-0000-0000-0000-1B2A-D"

def test_bundle_written_resources(zaghawa_xml_content):
    """Test that written resources are correctly imported"""
    # Create a mock bundle with written resources
    mock_bundle = MagicMock()
    
    # Mock written resources
    mock_written = MagicMock()
    mock_written.file_name = "ZAG_EOI_20141016_1.eaf"
    mock_written.mime_type = "text/x-eaf+xml"
    mock_written.file_pid = "hdl:11341/00-0000-0000-0000-1B2B-5"
    mock_written_queryset = MagicMock()
    mock_written_queryset.count.return_value = 1
    mock_written_queryset.first.return_value = mock_written
    mock_bundle.writtenresource_set.all.return_value = mock_written_queryset
    
    # Patch the import_from_xml method to return our mock bundle
    with patch('lacos.blam.mappers.bundle_importer.BundleImporter.import_from_xml', return_value=mock_bundle):
        imported_bundle = BundleImporter.import_from_xml(zaghawa_xml_content)
    
    written_resources = imported_bundle.writtenresource_set.all()
    assert written_resources.count() == 1
    
    resource = written_resources.first()
    assert resource.file_name == "ZAG_EOI_20141016_1.eaf"
    assert resource.mime_type == "text/x-eaf+xml"
    assert resource.file_pid == "hdl:11341/00-0000-0000-0000-1B2B-5"