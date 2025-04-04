import pytest
from unittest.mock import patch

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.mappers.bundle.read.import_bundle_administrative_info import import_administrative_info
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleAdministrativeInfo,
    BundleIdenticalResource,
    BundleLicense,
    BundleRightsHolder,
    BundleRightsHolderIdentifier
)


@pytest.fixture
def test_bundle():
    """Create a test bundle for testing."""
    return Bundle.objects.create(identifier="test-administrative-info-bundle")

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
    # Get the administrative info from CMD data
    admin_info = real_cmd_data.components.blam_bundle_repository_v1_0.bundle_administrative_info

    # Verify basic fields
    assert admin_info.access.value.value == "open"  # Access the actual enum value
    # Format XmlDate for comparison - only YYYY-MM-DD without timezone
    date_obj = admin_info.availability_date
    date_str = f"{date_obj.year}-{date_obj.month:02d}-{date_obj.day:02d}"
    assert date_str == "2018-11-29"
    
    # Verify license
    assert admin_info.license is not None
    assert len(admin_info.license) > 0  # Check it's a non-empty list
    license_info = admin_info.license[0]  # Get the first license
    assert license_info.license_name == ""  # Empty string instead of None
    assert license_info.license_identifier == ""  # Empty string instead of None
    
    # Verify rights holder
    assert admin_info.rights_holder is not None
    assert len(admin_info.rights_holder) == 1
    rights_holder = admin_info.rights_holder[0]
    assert rights_holder.rights_holder_name == "Birgit Hellwig"
    assert len(rights_holder.rights_holder_identifier) == 1
    assert rights_holder.rights_holder_identifier[0].value == "http://www.isni.org/0000000114600742"


@pytest.mark.django_db
def test_administrative_info_data_mapping(real_cmd_data, test_bundle):
    """Test that administrative info is mapped correctly from CMD to Django model"""
    # Test import with real data
    admin_info = import_administrative_info(real_cmd_data, test_bundle)
    
    # Verify the object was created and fields were set correctly
    assert isinstance(admin_info, BundleAdministrativeInfo)
    assert admin_info.availability_date == "2018-11-29"  # Without timezone
    
    # Verify license was created
    assert admin_info.licenses.count() == 1
    license = admin_info.licenses.first()
    assert license.license_name == ""  # Empty string instead of None
    assert license.license_identifier == ""  # Empty string instead of None
    assert license.access == "open"
    
    # Verify rights holder was created
    assert admin_info.rights_holders.count() == 1
    rights_holder = admin_info.rights_holders.first()
    assert rights_holder.rights_holder_name == "Birgit Hellwig"
    
    # Verify rights holder identifier
    assert rights_holder.rights_holder_identifiers.count() == 1
    identifier = rights_holder.rights_holder_identifiers.first()
    assert identifier.identifier == "http://www.isni.org/0000000114600742"
    assert identifier.identifier_type == "ISNI"
    
    # Verify the association with the bundle
    assert test_bundle.administrative_info.count() == 1
    assert test_bundle.administrative_info.first() == admin_info


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data, test_bundle):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    admin_info1 = import_administrative_info(real_cmd_data, test_bundle)
    
    # Second import with same data should get existing record
    admin_info2 = import_administrative_info(real_cmd_data, test_bundle)
    
    # Should be the same record
    assert admin_info1.pk == admin_info2.pk
    
    # Count should still be 1
    count = BundleAdministrativeInfo.objects.count()
    assert count == 1
    
    # Verify related objects weren't duplicated
    assert BundleLicense.objects.count() == 1
    assert BundleRightsHolder.objects.count() == 1
    assert BundleRightsHolderIdentifier.objects.count() == 1
    
    # Should only have one admin_info related to the bundle
    assert test_bundle.administrative_info.count() == 1 