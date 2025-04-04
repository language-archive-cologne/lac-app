import pytest
from unittest.mock import patch
from datetime import date
from xsdata.models.datatype import XmlDate

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_license import import_collection_license, create_collection_license
from lacos.blam.models.collection.collection_administrative_info import CollectionLicense, CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_repository import Collection
from blam_schemas.collection.blam_collection_repository_v1_0 import SimpletypeAccess41


@pytest.fixture
def test_collection():
    """Create a test collection for testing"""
    return Collection.objects.create()


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
def cmd_data():
    """Create sample CMD data for testing"""
    cmd = type('obj', (object,), {})
    cmd.components = type('obj', (object,), {})
    cmd.components.blam_collection_repository_v1_0 = type('obj', (object,), {})
    
    # Create repository component
    repo = cmd.components.blam_collection_repository_v1_0
    repo.collection_administrative_info = type('obj', (object,), {})
    
    # Create administrative info with license
    admin_info = repo.collection_administrative_info
    admin_info.license = [type('obj', (object,), {
        'license_name': 'Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany',
        'license_identifier': 'CC BY-NC-ND 3.0 DE'
    })]
    admin_info.access = type('obj', (object,), {'value': SimpletypeAccess41.OPEN})
    
    # Add availability_date as XmlDate
    admin_info.availability_date = XmlDate(2023, 1, 1)
    
    return cmd


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the administrative info component
    admin_info = real_cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    
    # Verify basic fields from algerien.xml
    assert len(admin_info.license) == 1
    assert admin_info.license[0].license_name == "Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany"
    assert admin_info.license[0].license_identifier == "CC BY-NC-ND 3.0 DE"


@pytest.mark.django_db
def test_license_data_mapping(real_cmd_data, test_collection):
    """Test that license data is mapped correctly from CMD to Django model"""
    # Test import with real data
    license_model = import_collection_license(real_cmd_data, test_collection)
    
    # Verify the license was created with correct values
    assert isinstance(license_model, CollectionLicense)
    assert license_model.license_name == "Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany"
    assert license_model.license_identifier == "CC BY-NC-ND 3.0 DE"
    assert license_model.access == "open"
    
    # Verify the license is associated with the collection via admin_info
    admin_info = CollectionAdministrativeInfo.objects.get(collection=test_collection)
    assert license_model in admin_info.licenses.all()


@pytest.mark.django_db
def test_missing_data_handling(cmd_data, test_collection):
    """Test handling of missing license data"""
    # Remove license data
    admin_info = cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    admin_info.license = []
    
    # Import should still work but return None
    license_model = import_collection_license(cmd_data, test_collection)
    
    # Verify no license was created
    assert license_model is None
    
    # Verify an admin_info was still created for the collection
    assert CollectionAdministrativeInfo.objects.filter(collection=test_collection).exists()
    admin_info = CollectionAdministrativeInfo.objects.get(collection=test_collection)
    assert admin_info.licenses.count() == 0


@pytest.mark.django_db
def test_missing_identifier_handling(cmd_data, test_collection):
    """Test handling of missing license identifier"""
    # Remove identifier but keep license name
    admin_info = cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    admin_info.license = [type('obj', (object,), {
        'license_name': 'Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany'
    })]
    
    # Import should work with missing identifier
    license_model = import_collection_license(cmd_data, test_collection)
    
    # Verify values
    assert isinstance(license_model, CollectionLicense)
    assert license_model.license_name == "Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany"
    assert license_model.license_identifier == ""  # Empty string for missing identifier


@pytest.mark.django_db
def test_create_collection_license(cmd_data):
    """Test creating a CollectionLicense model instance"""
    admin_info = cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    
    # Create license model
    license_model = create_collection_license(admin_info)
    
    # Verify the model was created correctly
    assert isinstance(license_model, CollectionLicense)
    assert license_model.license_name == "Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Germany"
    assert license_model.license_identifier == "CC BY-NC-ND 3.0 DE"
    assert license_model.access == "open"


@pytest.mark.django_db
def test_get_or_create_behavior(cmd_data):
    """Test that creating the same license twice doesn't create duplicates"""
    admin_info = cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    
    # First creation
    license1 = create_collection_license(admin_info)
    
    # Second creation with same data
    license2 = create_collection_license(admin_info)
    
    # Should be the same record
    assert license1.pk == license2.pk
    
    # Count should still be 1
    assert CollectionLicense.objects.count() == 1


@pytest.mark.django_db
def test_access_type_mapping(cmd_data):
    """Test that access types are correctly mapped from schema to model"""
    admin_info = cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    
    # Test different access types
    access_mappings = {
        SimpletypeAccess41.OPEN: "open",
        SimpletypeAccess41.REGISTRATION_REQUIRED: "registration_required",
        SimpletypeAccess41.REQUEST_REQUIRED: "request_required"
    }
    
    for schema_access, model_access in access_mappings.items():
        admin_info.access = type('obj', (object,), {'value': schema_access})
        license_model = create_collection_license(admin_info)
        assert license_model.access == model_access 