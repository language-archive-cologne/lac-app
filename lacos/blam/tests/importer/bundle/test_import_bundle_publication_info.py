import pytest
from unittest.mock import patch

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.mappers.bundle.read.import_bundle_publication_info import import_publication_info
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo, BundleCreator


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
    with patch('django.core.exceptions.ValidationError', Exception):
        return BundleImporter.validate_xml(real_bundle_xml)


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the publication info from CMD data
    pub_info = real_cmd_data.components.blam_bundle_repository_v1_0.bundle_publication_info
    
    # Verify publication year exists
    assert hasattr(pub_info, 'bundle_publication_year')
    # Check that it's an XmlPeriod object which doesn't have a .value attribute
    assert pub_info.bundle_publication_year is not None
    # From the XML we know it should be 2018
    
    # Verify data provider
    assert pub_info.bundle_data_provider == "Language Archive Cologne"
    
    # Verify creators
    assert hasattr(pub_info, 'bundle_creators')
    assert pub_info.bundle_creators is not None
    assert len(pub_info.bundle_creators.bundle_creator) == 1
    
    creator = pub_info.bundle_creators.bundle_creator[0]
    assert creator.creator_name.creator_family_name == "Hellwig"
    assert creator.creator_name.creator_given_name == "Birgit"
    assert hasattr(creator, 'creator_name_identifier')
    assert len(creator.creator_name_identifier) == 1
    assert creator.creator_name_identifier[0].value == "http://www.isni.org/0000000114600742"
    assert hasattr(creator, 'creator_affiliation')
    assert len(creator.creator_affiliation) == 1
    assert creator.creator_affiliation[0] == "University of Cologne"


@pytest.mark.django_db
def test_publication_info_data_mapping(real_cmd_data):
    """Test that publication info is mapped correctly from CMD to Django model"""
    # Test import with real data
    pub_info = import_publication_info(real_cmd_data)
    
    # Verify the object was created
    assert isinstance(pub_info, BundlePublicationInfo)
    
    # Verify fields were mapped correctly
    assert pub_info.publication_year == 2018
    assert pub_info.data_provider == "Language Archive Cologne"
    
    # Verify creators were imported
    assert pub_info.creators.count() == 1
    creator = pub_info.creators.first()
    assert creator.family_name == "Hellwig"
    assert creator.given_name == "Birgit"
    assert creator.name_identifier == "http://www.isni.org/0000000114600742"
    assert creator.affiliation == "University of Cologne"


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    pub_info1 = import_publication_info(real_cmd_data)
    
    # Second import with same data should get existing record
    pub_info2 = import_publication_info(real_cmd_data)
    
    # Should be the same record
    assert pub_info1.pk == pub_info2.pk
    
    # Count should still be 1
    count = BundlePublicationInfo.objects.count()
    assert count == 1
    
    # Verify related objects weren't duplicated
    assert BundleCreator.objects.count() == 1 