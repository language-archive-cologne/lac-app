import pytest
from unittest.mock import patch

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_administrative_info import import_administrative_info
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionIdenticalResource,
    CollectionLicense,
    CollectionRightsHolder,
    CollectionRightsHolderIdentifier
)
from lacos.blam.models.collection.collection_repository import Collection
from blam_schemas.collection.blam_collection_repository_v1_0 import SimpletypeAccess41


@pytest.fixture
def test_collection():
    """Create a test collection for testing."""
    return Collection.objects.create(identifier="test-collection-administrative-info")


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


@pytest.fixture
def mock_admin_info():
    """Create a mock admin info schema with configurable fields"""
    class MockAdminInfo:
        def __init__(self, access_value=SimpletypeAccess41.OPEN, licenses=None, rights_holders=None):
            self.access = type('Access', (), {'value': access_value})()
            # Only set license if provided, otherwise don't set it at all
            if licenses is not None:
                self.license = licenses
            self.rights_holder = rights_holders or []
            self.collection_is_identical_to = []
            self.collection_is_derivation_of = None
            self.availability_date = type('Date', (), {'year': 2022, 'month': 10, 'day': 26})()
    
    return MockAdminInfo


@pytest.fixture
def mock_cmd_data(mock_admin_info):
    """Create a mock CMD data with configurable admin info"""
    def create_cmd(admin_info):
        return type('Cmd', (), {
            'components': type('Components', (), {
                'blam_collection_repository_v1_0': type('Repo', (), {
                    'collection_administrative_info': admin_info
                })()
            })()
        })()
    return create_cmd


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the administrative info from CMD data
    admin_info = real_cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    
    # Verify basic fields
    assert admin_info.access.value.value == "open"  # Access the actual enum value
    
    # Format XmlDate for comparison - only YYYY-MM-DD without timezone
    date_obj = admin_info.availability_date
    date_str = f"{date_obj.year}-{date_obj.month:02d}-{date_obj.day:02d}"
    assert date_str == "2022-10-26"  # Actual date from the XML
    
    # Verify identical resources
    assert hasattr(admin_info, 'collection_is_identical_to')
    
    # Verify derivation URI
    assert hasattr(admin_info, 'collection_is_derivation_of')
    
    # Verify license
    assert admin_info.license is not None
    assert len(admin_info.license) > 0  # Check it's a non-empty list
    license_info = admin_info.license[0]  # Get the first license
    assert license_info.license_name == "Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany"
    assert license_info.license_identifier == "CC BY-NC-ND 3.0 DE"
    
    # Verify rights holder
    assert admin_info.rights_holder is not None
    assert len(admin_info.rights_holder) == 1
    rights_holder = admin_info.rights_holder[0]
    assert rights_holder.rights_holder_name == "LAC"  # Updated to match XML
    assert len(rights_holder.rights_holder_identifier) == 1
    identifier = rights_holder.rights_holder_identifier[0]
    assert identifier.identifier_type.value == "ORCID"  # Updated to match XML
    assert not identifier.value  # XML has empty value


@pytest.mark.django_db
def test_administrative_info_data_mapping(real_cmd_data, test_collection):
    """Test that administrative info is mapped correctly from CMD to Django model"""
    # Test import with real data
    admin_info = import_administrative_info(real_cmd_data, test_collection)
    
    # Verify the object was created and fields were set correctly
    assert isinstance(admin_info, CollectionAdministrativeInfo)
    assert admin_info.availability_date == "2022-10-26"  # Actual date from XML
    assert admin_info.collection == test_collection
    
    # Verify identical resources if any
    if hasattr(admin_info, 'is_identical_to'):
        for identical_resource in admin_info.is_identical_to.all():
            assert isinstance(identical_resource, CollectionIdenticalResource)
            assert identical_resource.uri  # URI should not be empty
    
    # Verify derivation URI if exists
    if admin_info.is_derivation_of:  # Changed to check the attribute value instead of type
        assert isinstance(admin_info.is_derivation_of, str)
    
    # Verify license was created
    assert admin_info.licenses.count() == 1
    license = admin_info.licenses.first()
    assert license.license_name == "Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany"
    assert license.license_identifier == "CC BY-NC-ND 3.0 DE"
    assert license.access == "open"
    
    # Verify rights holder was created
    assert admin_info.rights_holders.count() == 1
    rights_holder = admin_info.rights_holders.first()
    assert rights_holder.rights_holder_name == "LAC"  # Updated to match XML
    
    # Verify rights holder identifier
    assert rights_holder.rights_holder_identifiers.count() == 1
    identifier = rights_holder.rights_holder_identifiers.first()
    assert identifier.identifier_type == "ORCID"  # Updated to match XML
    assert not identifier.identifier  # XML has empty value


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data, test_collection):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    admin_info1 = import_administrative_info(real_cmd_data, test_collection)
    
    # Second import with same data should get existing record
    admin_info2 = import_administrative_info(real_cmd_data, test_collection)
    
    # Should be the same record
    assert admin_info1.pk == admin_info2.pk
    
    # Count should still be 1
    count = CollectionAdministrativeInfo.objects.filter(collection=test_collection).count()
    assert count == 1
    
    # Verify related objects weren't duplicated
    assert CollectionLicense.objects.count() == 1
    assert CollectionRightsHolder.objects.count() == 1
    assert CollectionRightsHolderIdentifier.objects.count() == 1
    assert CollectionIdenticalResource.objects.count() == 0  # No identical resources in test data


@pytest.mark.django_db
def test_access_type_mapping(mock_admin_info, mock_cmd_data, test_collection):
    """Test that access types are correctly mapped from schema to model"""
    # Test different access types
    access_mappings = {
        SimpletypeAccess41.OPEN: "open",
        SimpletypeAccess41.REGISTRATION_REQUIRED: "registration_required",
        SimpletypeAccess41.REQUEST_REQUIRED: "request_required"
    }
    
    for schema_access, model_access in access_mappings.items():
        # Create a mock license to test access type mapping
        mock_license = type('License', (), {
            'license_name': 'Test License',
            'license_identifier': 'TEST-1.0'
        })()
        admin_info = mock_admin_info(access_value=schema_access, licenses=[mock_license])
        result = import_administrative_info(mock_cmd_data(admin_info), test_collection)
        assert result.licenses.first().access == model_access
        assert result.collection == test_collection


@pytest.mark.django_db
def test_relationships_are_created(real_cmd_data, test_collection):
    """Test that all relationships are properly created in the database"""
    # Import the data
    admin_info = import_administrative_info(real_cmd_data, test_collection)
    
    # Verify CollectionAdministrativeInfo relationships
    # 1. collection relationship
    assert admin_info.collection == test_collection
    
    # 2. licenses relationship
    assert admin_info.licenses.exists()
    license = admin_info.licenses.first()
    
    # Verify the reverse relationship works - the related_name in the model is 'licenses'
    assert admin_info in license.licenses.all()
    
    # 3. rights_holders relationship
    assert admin_info.rights_holders.exists()
    rights_holder = admin_info.rights_holders.first()
    # Verify the reverse relationship works - the related_name in the model is 'rights_holders'
    assert admin_info in rights_holder.rights_holders.all()
    
    # 4. is_identical_to relationship (should be empty in test data)
    assert not admin_info.is_identical_to.exists()
    
    # Verify CollectionRightsHolder relationships
    # 1. rights_holder_identifiers relationship
    assert rights_holder.rights_holder_identifiers.exists()
    identifier = rights_holder.rights_holder_identifiers.first()
    # Verify the reverse relationship works
    assert rights_holder in identifier.rights_holders_identifiers.all()


@pytest.mark.django_db
def test_multiple_licenses(mock_admin_info, mock_cmd_data, test_collection):
    """Test handling of multiple licenses"""
    # Create mock admin info with multiple licenses
    licenses = [
        type('License', (), {
            'license_name': 'First License',
            'license_identifier': 'LICENSE-1.0'
        })(),
        type('License', (), {
            'license_name': 'Second License',
            'license_identifier': 'LICENSE-2.0'
        })()
    ]
    admin_info = mock_admin_info(licenses=licenses)
    
    # Import and verify
    result = import_administrative_info(mock_cmd_data(admin_info), test_collection)
    assert result.licenses.count() == 2
    assert result.collection == test_collection
    
    # Verify both licenses were created correctly
    licenses = result.licenses.all()
    assert licenses[0].license_name == 'First License'
    assert licenses[0].license_identifier == 'LICENSE-1.0'
    assert licenses[1].license_name == 'Second License'
    assert licenses[1].license_identifier == 'LICENSE-2.0'


@pytest.mark.django_db
def test_missing_license_data(mock_admin_info, mock_cmd_data, test_collection):
    """Test handling of missing license data"""
    # Create mock admin info with no licenses
    admin_info = mock_admin_info(licenses=[])
    
    # Import and verify
    result = import_administrative_info(mock_cmd_data(admin_info), test_collection)
    assert result.licenses.count() == 0
    assert result.collection == test_collection


@pytest.mark.django_db
def test_invalid_data_handling(mock_admin_info, mock_cmd_data, test_collection):
    """Test handling of invalid data"""
    # Test with invalid license data
    invalid_license = type('License', (), {
        'license_name': None,  # Invalid: should be string
        'license_identifier': ''  # Invalid: should be non-empty
    })()
    admin_info = mock_admin_info(licenses=[invalid_license])
    
    # Import should still work but create empty license
    result = import_administrative_info(mock_cmd_data(admin_info), test_collection)
    assert result.collection == test_collection
    assert result.licenses.count() == 1
    license = result.licenses.first()
    assert license.license_name == ''  # Empty string fallback
    assert license.license_identifier == ''  # Empty is allowed
