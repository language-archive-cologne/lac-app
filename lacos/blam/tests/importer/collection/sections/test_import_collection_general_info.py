import pytest
from unittest.mock import patch

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_general_info import import_general_info, import_keywords
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
    CollectionObjectLanguage,
    CollectionObjectLanguageAlternativeName,
    CollectionObjectLanguageTaxonomy,
    CollectionObjectLanguageLanguageFamily
)


@pytest.fixture
def real_collection_xml():
    """Get the XML content from a real collection file in the data directory."""
    import os
    xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        alternate_paths = [
            os.path.join('data', 'algerien', 'v1', 'content', 'algerien.xml'),
            os.path.join('data', 'formatted', 'algerien.xml')
        ]
        for path in alternate_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                continue
        
        raise FileNotFoundError(f"Could not find collection XML file at {xml_path} or alternate locations")


@pytest.fixture
def real_cmd_data(real_collection_xml):
    """Parse real collection XML into CMD data"""
    with patch('django.core.exceptions.ValidationError', Exception):
        return CollectionImporter.validate_xml(real_collection_xml)


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the general info from CMD data
    general_info = real_cmd_data.components.blam_collection_repository_v1_0.collection_general_info
    
    # Verify basic fields
    assert general_info.collection_display_title == "Interviews about Rock Art"
    assert general_info.collection_description == "The Interviews were made by Issak Oukafi Cheikh for his Master Thesis 'L'historie d'Eharir (Tassili n Azjer, Sahara) dans la perception locale de l'art rupestre'. He talked with several locals from the village Eharir in western Algeria in 2010/2011 about thier perception of ancient rock art in the region."
    assert general_info.collection_version == "1"
    
    # Verify collection ID
    assert general_info.collection_id[0].value == "hdl:11341/0000-0000-0000-3D7C"
    assert general_info.collection_id[0].identifier_type.value == "Handle"
    
    # Verify location
    location = general_info.collection_location
    assert location.collection_geo_location == "25.395833333333332, 8.402777777777779"
    assert location.collection_location_facet == "Iherir"
    assert location.collection_region_facet == "Bordj El Haouas"
    assert location.collection_country_facet == "Algerien"
    assert location.collection_country_code.value == "DZ"
    
    # Verify languages
    languages = general_info.collection_object_languages.collection_object_language
    assert len(languages) == 1
    lang = languages[0]
    assert lang.object_language_display_name[0] == "Tamasheq"
    assert lang.object_language_name == "Tamasheq"
    assert lang.object_language_iso639_3_code.value == "taq"
    assert lang.object_language_glottolog_code.value == "tama1365"
    
    # Verify alternative names
    alt_names = lang.object_language_alternative_names.object_language_alternative_name
    # Filter out empty names for comparison
    non_empty_alt_names = [name for name in alt_names if name and name.strip()]
    assert len(non_empty_alt_names) == 16
    assert "Tamaceq" in non_empty_alt_names
    assert "Kidal Tamasheq" in non_empty_alt_names
    assert "Tomacheck" in non_empty_alt_names
    assert "Tamasheq" in non_empty_alt_names
    assert "Kidal" in non_empty_alt_names
    assert "Mali Tamasheq" in non_empty_alt_names
    assert "Tuareg" in non_empty_alt_names
    assert "Tamäšeq" in non_empty_alt_names
    
    # Verify language taxonomy
    taxonomy = lang.object_language_taxonomy
    assert taxonomy.object_language_language_family == ["Afro-Asiatic"]


@pytest.mark.django_db
def test_general_info_data_mapping(real_cmd_data):
    """Test that general info is mapped correctly from CMD to Django model"""
    # Test import with real data
    general_info = import_general_info(real_cmd_data)
    
    # Verify the object was created and fields were set correctly
    assert isinstance(general_info, CollectionGeneralInfo)
    assert general_info.display_title == "Interviews about Rock Art"
    assert general_info.description == "The Interviews were made by Issak Oukafi Cheikh for his Master Thesis 'L'historie d'Eharir (Tassili n Azjer, Sahara) dans la perception locale de l'art rupestre'. He talked with several locals from the village Eharir in western Algeria in 2010/2011 about thier perception of ancient rock art in the region."
    assert general_info.version == "1"
    assert general_info.id_value == "hdl:11341/0000-0000-0000-3D7C"
    assert general_info.id_type == "HANDLE"
    
    # Check location was created and linked
    assert general_info.location is not None
    assert isinstance(general_info.location, CollectionLocation)
    assert general_info.location.geo_location == "25.395833333333332, 8.402777777777779"
    assert general_info.location.location_facet == "Iherir"
    assert general_info.location.region_facet == "Bordj El Haouas"
    assert general_info.location.country_facet == "Algerien"
    assert general_info.location.country_code == "DZ"
    
    # Verify languages were imported
    assert general_info.object_languages.count() == 1
    language = general_info.object_languages.first()
    assert language.display_name == "Tamasheq"
    assert language.name == "Tamasheq"
    assert language.iso_639_3_code == "taq"
    assert language.glottolog_code == "tama1365"
    
    # Verify alternative names
    alt_names = list(language.alternative_names.all().values_list('value', flat=True))
    assert len(alt_names) == 16
    assert "Tamaceq" in alt_names
    assert "Kidal Tamasheq" in alt_names
    assert "Tomacheck" in alt_names
    assert "Tamasheq" in alt_names
    assert "Kidal" in alt_names
    assert "Mali Tamasheq" in alt_names
    assert "Tuareg" in alt_names
    assert "Tamäšeq" in alt_names
    
    # Verify language taxonomy
    taxonomy = language.taxonomy
    assert taxonomy is not None
    families = list(taxonomy.language_family.all().values_list('value', flat=True))
    assert "Afro-Asiatic" in families

    # Create mock data with test keywords
    mock_data = {
        'collection_keywords': {
            'collection_keyword': [
                'Rock Art',
                'Interviews',
                'Algeria',
                'Tassili n Azjer',
                'Eharir',
                '',  # Empty keyword that should be skipped
                ' ',  # Whitespace keyword that should be skipped
                'Sahara'
            ]
        }
    }
    
    # Import keywords
    import_keywords(general_info, mock_data['collection_keywords'])
    
    # Verify keywords were imported correctly
    keywords = list(general_info.keywords.all().values_list('value', flat=True))
    assert len(keywords) == 6  # Only non-empty keywords should be imported
    assert 'Rock Art' in keywords
    assert 'Interviews' in keywords
    assert 'Algeria' in keywords
    assert 'Tassili n Azjer' in keywords
    assert 'Eharir' in keywords
    assert 'Sahara' in keywords
    
    # Verify CollectionKeyword objects were created
    assert CollectionKeyword.objects.count() == 6
    # Verify empty keywords were not created
    assert not CollectionKeyword.objects.filter(value='').exists()
    assert not CollectionKeyword.objects.filter(value=' ').exists()


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    general_info1 = import_general_info(real_cmd_data)
    
    # Second import with same ID should get existing record
    general_info2 = import_general_info(real_cmd_data)
    
    # Should be the same record
    assert general_info1.pk == general_info2.pk
    
    # Count should still be 1
    count = CollectionGeneralInfo.objects.filter(id_value="hdl:11341/0000-0000-0000-3D7C").count()
    assert count == 1
    
    # Verify related objects weren't duplicated
    assert CollectionLocation.objects.count() == 1
    assert CollectionObjectLanguage.objects.count() == 1
    assert CollectionObjectLanguageAlternativeName.objects.count() == 16  # Number of non-empty alternative names in XML
    assert CollectionObjectLanguageTaxonomy.objects.count() == 1
    assert CollectionObjectLanguageLanguageFamily.objects.count() == 1


@pytest.mark.django_db
def test_relationships_are_created(real_cmd_data):
    """Test that all relationships in CollectionGeneralInfo are created properly"""
    # Import the general info
    general_info = import_general_info(real_cmd_data)
    
    # Import keywords first
    mock_data = {
        'collection_keywords': {
            'collection_keyword': [
                'Rock Art',
                'Interviews',
                'Algeria',
                'Tassili n Azjer',
                'Eharir',
                '',  # Empty keyword that should be skipped
                ' ',  # Whitespace keyword that should be skipped
                'Sahara'
            ]
        }
    }
    import_keywords(general_info, mock_data['collection_keywords'])
    
    # 1. Verify CollectionGeneralInfo relationships
    # Check location relationship (ForeignKey)
    assert general_info.location is not None
    assert isinstance(general_info.location, CollectionLocation)
    assert general_info.location.geo_location == "25.395833333333332, 8.402777777777779"
    
    # Check keywords relationship (ManyToMany)
    assert general_info.keywords.count() == 6  # Number of non-empty keywords
    keywords = list(general_info.keywords.all().values_list('value', flat=True))
    assert "Rock Art" in keywords
    assert "Interviews" in keywords
    
    # Check object languages relationship (ManyToMany)
    assert general_info.object_languages.count() == 1
    language = general_info.object_languages.first()
    assert language.name == "Tamasheq"
    
    # 2. Verify CollectionObjectLanguage relationships
    # Check alternative names relationship (ManyToMany)
    assert language.alternative_names.count() == 16  # Number of non-empty alternative names
    alt_names = list(language.alternative_names.all().values_list('value', flat=True))
    assert "Tamaceq" in alt_names
    assert "Kidal Tamasheq" in alt_names
    
    # Check taxonomy relationship (OneToOne)
    assert language.taxonomy is not None
    assert language.taxonomy.language_family.count() == 1
    families = list(language.taxonomy.language_family.all().values_list('value', flat=True))
    assert "Afro-Asiatic" in families
    
    # 3. Verify reverse relationships
    # Check reverse relationship from CollectionLocation to CollectionGeneralInfo (ForeignKey)
    assert general_info.location.collection_general_info.filter(id=general_info.id).exists()
    
    # Check reverse relationship from CollectionKeyword to CollectionGeneralInfo (ManyToMany)
    keyword = general_info.keywords.first()
    assert keyword.collectiongeneralinfo_set.filter(id=general_info.id).exists()
    
    # Check reverse relationship from CollectionObjectLanguage to CollectionGeneralInfo (ManyToMany)
    assert language.collectiongeneralinfo_set.filter(id=general_info.id).exists()
    
    # Check reverse relationship from CollectionObjectLanguageAlternativeName to CollectionObjectLanguage (ManyToMany)
    alt_name = language.alternative_names.first()
    assert alt_name.collectionobjectlanguage_set.filter(id=language.id).exists()
    
    # Check reverse relationship from CollectionObjectLanguageTaxonomy to CollectionObjectLanguage (OneToOne)
    assert language.taxonomy.object_language == language
    
    # Check reverse relationship from CollectionObjectLanguageLanguageFamily to CollectionObjectLanguageTaxonomy (ManyToMany)
    family = language.taxonomy.language_family.first()
    assert family.collectionobjectlanguagetaxonomy_set.filter(id=language.taxonomy.id).exists()


@pytest.mark.django_db
def test_language_update_behavior(real_cmd_data):
    """Test that re-importing updates existing language data based on ISO code."""
    # First import
    import_general_info(real_cmd_data)
    assert CollectionObjectLanguage.objects.count() == 1
    lang1 = CollectionObjectLanguage.objects.get(iso_639_3_code='taq')
    assert lang1.name == "Tamasheq" 
    assert lang1.glottolog_code == "tama1365"

    # Modify the name in the source data for the second import
    real_cmd_data.components.blam_collection_repository_v1_0.collection_general_info.collection_object_languages.collection_object_language[0].object_language_name = "Tamasheq_Updated"
    # Modify glottolog code as well
    real_cmd_data.components.blam_collection_repository_v1_0.collection_general_info.collection_object_languages.collection_object_language[0].object_language_glottolog_code.value = "xxxx1111"


    # Second import
    import_general_info(real_cmd_data)
    
    # Count should still be 1 (no new language created)
    assert CollectionObjectLanguage.objects.count() == 1
    
    # Verify the existing object was updated
    lang2 = CollectionObjectLanguage.objects.get(iso_639_3_code='taq')
    assert lang1.pk == lang2.pk # Should be the same object
    assert lang2.name == "Tamasheq_Updated" # Name should be updated
    assert lang2.glottolog_code == "xxxx1111" # Glottolog code should be updated 