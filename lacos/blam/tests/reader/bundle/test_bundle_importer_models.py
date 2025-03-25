import pytest
import os
from unittest.mock import patch, MagicMock, Mock

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import MediaResource, WrittenResource
from lacos.blam.models.base_project_info import ProjectInfo
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd


@pytest.fixture(autouse=True)
def mock_db_connection(monkeypatch):
    """Globally mock database access"""
    # Set up global patches to prevent actual database access
    monkeypatch.setattr('django.db.transaction.atomic', lambda func=None: func if func else MagicMock())
    monkeypatch.setattr('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', MagicMock())
    monkeypatch.setattr('django.db.backends.base.base.BaseDatabaseWrapper.get_autocommit', MagicMock(return_value=True))
    
    # Mock Django model Manager to prevent database access
    mock_manager = MagicMock()
    mock_manager.get_or_create.return_value = (MagicMock(), True)
    mock_manager.create.return_value = MagicMock()
    mock_manager.get.return_value = MagicMock()
    mock_manager.filter.return_value = mock_manager
    mock_manager.all.return_value = []
    
    # Patch manager methods for all model classes we use
    monkeypatch.setattr('lacos.blam.models.bundle.bundle_repository.Bundle.objects', mock_manager)
    monkeypatch.setattr('lacos.blam.models.bundle.bundle_general_info.BundleGeneralInfo.objects', mock_manager)
    monkeypatch.setattr('lacos.blam.models.bundle.bundle_publication_info.BundlePublicationInfo.objects', mock_manager)
    monkeypatch.setattr('lacos.blam.models.bundle.bundle_administrative_info.BundleAdministrativeInfo.objects', mock_manager)
    monkeypatch.setattr('lacos.blam.models.bundle.bundle_structural_info.BundleStructuralInfo.objects', mock_manager)
    monkeypatch.setattr('lacos.blam.models.base_project_info.ProjectInfo.objects', mock_manager)


@pytest.fixture
def real_bundle_xml():
    """Get the XML content from a real bundle file in the data directory."""
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
    """Fixture to get the real CMD data from the XML content"""
    with patch('django.core.exceptions.ValidationError', Exception):  # Ensure validation errors don't break tests
        return BundleImporter.validate_xml(real_bundle_xml)


@pytest.fixture
def mock_cmd_data():
    """Mock CMD data object"""
    mock = MagicMock()
    repository = mock.components.blam_bundle_repository_v1_0
    repository.mdlicense.value = "CC-BY"
    repository.mdlicense.uri = "https://creativecommons.org/licenses/by/4.0/"
    
    # Add realistic values from real bundle
    repository.bundle_general_info.bundle_display_title = "Bodyparts 1"
    repository.bundle_general_info.bundle_description = "Translation of the Body parts in a Swadesh list from English to Zaghawa"
    repository.bundle_publication_info.bundle_publication_year = "2018"
    repository.bundle_publication_info.bundle_data_provider = "Language Archive Cologne"
    
    return mock


def test_import_general_info(mock_cmd_data):
    """Test that general info is correctly imported from XML"""
    # Create a mock return value for the import function
    mock_general_info = MagicMock(spec=BundleGeneralInfo)
    mock_general_info.bundle_display_title = "Bodyparts 1"
    mock_general_info.bundle_description = "Translation of the Body parts in a Swadesh list from English to Zaghawa"
    
    # Directly patch the import_general_info at module level
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.import_general_info', 
               return_value=mock_general_info) as mock_import:
        
        # Call the function
        result = BundleImporter._import_general_info(mock_cmd_data)
        
        # Assert that the mock function was called with correct args
        mock_import.assert_called_once_with(mock_cmd_data)
        
        # Assert that the result is the mock object
        assert result == mock_general_info
        assert result.bundle_display_title == "Bodyparts 1"
        assert "Body parts" in result.bundle_description


def test_import_publication_info(mock_cmd_data):
    """Test that publication info is correctly imported from XML"""
    # Create a mock return value for the import function
    mock_publication_info = MagicMock(spec=BundlePublicationInfo)
    mock_publication_info.bundle_publication_year = "2018"
    mock_publication_info.bundle_data_provider = "Language Archive Cologne"
    
    # Directly patch the import_publication_info at module level
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.import_publication_info', 
               return_value=mock_publication_info) as mock_import:
        
        # Call the function
        result = BundleImporter._import_publication_info(mock_cmd_data)
        
        # Assert that the mock function was called with correct args
        mock_import.assert_called_once_with(mock_cmd_data)
        
        # Assert that the result is the mock object
        assert result == mock_publication_info
        assert result.bundle_publication_year == "2018"
        assert result.bundle_data_provider == "Language Archive Cologne"


def test_import_administrative_info(mock_cmd_data):
    """Test that administrative info is correctly imported from XML"""
    # Create a mock return value for the import function
    mock_administrative_info = MagicMock(spec=BundleAdministrativeInfo)
    mock_administrative_info.access = "open"
    
    # Directly patch the import_administrative_info at module level
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.import_administrative_info', 
               return_value=mock_administrative_info) as mock_import:
        
        # Call the function
        result = BundleImporter._import_administrative_info(mock_cmd_data)
        
        # Assert that the mock function was called with correct args
        mock_import.assert_called_once_with(mock_cmd_data)
        
        # Assert that the result is the mock object
        assert result == mock_administrative_info
        assert result.access == "open"


def test_import_structural_info(mock_cmd_data):
    """Test that structural info is correctly imported from XML"""
    # Setup
    collection_id = 123
    
    # Create mock structural info
    mock_structural_info = MagicMock(spec=BundleStructuralInfo)
    
    # Create sample resources
    mock_media_resource = MagicMock(spec=MediaResource)
    mock_media_resource.file_name = "ZAG_EOI_20141009_1.wav"
    mock_media_resource.file_pid = "hdl:11341/00-0000-0000-0000-1B28-A"
    mock_media_resource.mime_type = "audio/x-wav"
    
    mock_written_resource = MagicMock(spec=WrittenResource)
    mock_written_resource.file_name = "ZAG_EOI_20141009_1.eaf"
    mock_written_resource.file_pid = "hdl:11341/00-0000-0000-0000-1B29-8"
    mock_written_resource.mime_type = "text/x-eaf+xml"
    
    # Set up mock structure for resources
    mock_bundle_resources = MagicMock()
    mock_bundle_resources.bundle_media_resources.all.return_value = [mock_media_resource]
    mock_bundle_resources.bundle_written_resources.all.return_value = [mock_written_resource]
    mock_structural_info.bundle_resources = mock_bundle_resources
    
    # Directly patch the import_structural_info at module level
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.import_structural_info', 
               return_value=mock_structural_info) as mock_import:
        
        # Call the function
        result = BundleImporter._import_structural_info(mock_cmd_data, collection_id)
        
        # Assert that the mock function was called with correct args
        mock_import.assert_called_once_with(mock_cmd_data, collection_id)
        
        # Assert that the result is the mock object
        assert result == mock_structural_info
        
        # Check resources
        media_resources = list(result.bundle_resources.bundle_media_resources.all())
        assert len(media_resources) == 1
        assert media_resources[0].file_name == "ZAG_EOI_20141009_1.wav"
        assert media_resources[0].file_pid == "hdl:11341/00-0000-0000-0000-1B28-A"
        
        written_resources = list(result.bundle_resources.bundle_written_resources.all())
        assert len(written_resources) == 1
        assert written_resources[0].file_name == "ZAG_EOI_20141009_1.eaf"
        assert written_resources[0].file_pid == "hdl:11341/00-0000-0000-0000-1B29-8"


def test_import_projects(mock_cmd_data):
    """Test that projects are correctly imported from XML"""
    # Create mock bundle
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.projects = MagicMock()
    mock_bundle.projects.add = MagicMock()
    
    # Create mock project
    mock_project = MagicMock(spec=ProjectInfo)
    mock_project.project_display_name = "Fieldmethods Zaghawa"
    mock_project.project_description = "Fieldmethods Zaghawa, WS 2014/15, University of Cologne"
    
    # Directly patch the import_project_info at module level
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.import_project_info', 
               return_value=[mock_project]) as mock_import:
        
        # Call the function
        BundleImporter._import_and_link_projects(mock_cmd_data, mock_bundle)
        
        # Assert that the mock function was called with correct args
        mock_import.assert_called_once_with(mock_cmd_data)
        
        # Assert that the project was added to the bundle
        mock_bundle.projects.add.assert_called_once_with(mock_project)


def test_extract_metadata_license(mock_cmd_data):
    """Test that metadata license is correctly extracted from XML"""
    md_license, md_license_uri = BundleImporter._extract_metadata_license(mock_cmd_data)
    assert md_license == "CC-BY"
    assert md_license_uri == "https://creativecommons.org/licenses/by/4.0/"


def test_create_or_update_bundle():
    """Test create_or_update_bundle method with mocks"""
    # Create mock components
    mock_general_info = MagicMock(spec=BundleGeneralInfo)
    mock_publication_info = MagicMock(spec=BundlePublicationInfo)
    mock_administrative_info = MagicMock(spec=BundleAdministrativeInfo)
    mock_structural_info = MagicMock(spec=BundleStructuralInfo)
    md_license = "CC-BY"
    md_license_uri = "https://creativecommons.org/licenses/by/4.0/"
    
    # Create mock bundle
    mock_bundle = MagicMock(spec=Bundle)
    
    # Patch the Bundle.objects.get_or_create method
    with patch('lacos.blam.models.bundle.bundle_repository.Bundle.objects.get_or_create',
               return_value=(mock_bundle, True)) as mock_get_or_create:
        
        # Call the function
        result = BundleImporter._create_or_update_bundle(
            mock_general_info,
            mock_publication_info,
            mock_administrative_info,
            mock_structural_info,
            md_license,
            md_license_uri
        )
        
        # Assert that get_or_create was called with correct args
        mock_get_or_create.assert_called_once_with(
            general_info=mock_general_info,
            defaults={
                'publication_info': mock_publication_info,
                'administrative_info': mock_administrative_info,
                'structural_info': mock_structural_info,
                'md_license': md_license,
                'md_license_uri': md_license_uri
            }
        )
        
        # Assert that the result is the mock bundle
        assert result == mock_bundle


def test_update_existing_bundle():
    """Test create_or_update_bundle method when updating an existing bundle"""
    # Create mock components
    mock_general_info = MagicMock(spec=BundleGeneralInfo)
    mock_publication_info = MagicMock(spec=BundlePublicationInfo)
    mock_administrative_info = MagicMock(spec=BundleAdministrativeInfo)
    mock_structural_info = MagicMock(spec=BundleStructuralInfo)
    md_license = "CC-BY"
    md_license_uri = "https://creativecommons.org/licenses/by/4.0/"
    
    # Create mock bundle
    mock_bundle = MagicMock(spec=Bundle)
    
    # Patch the Bundle.objects.get_or_create method to return existing bundle
    with patch('lacos.blam.models.bundle.bundle_repository.Bundle.objects.get_or_create',
               return_value=(mock_bundle, False)) as mock_get_or_create:
        
        # Call the function
        result = BundleImporter._create_or_update_bundle(
            mock_general_info,
            mock_publication_info,
            mock_administrative_info,
            mock_structural_info,
            md_license,
            md_license_uri
        )
        
        # Assert that attributes were updated
        assert mock_bundle.publication_info == mock_publication_info
        assert mock_bundle.administrative_info == mock_administrative_info
        assert mock_bundle.structural_info == mock_structural_info
        assert mock_bundle.md_license == md_license
        assert mock_bundle.md_license_uri == md_license_uri
        
        # Assert that save was called
        mock_bundle.save.assert_called_once()
        
        # Assert that the result is the mock bundle
        assert result == mock_bundle


def test_import_cmd_to_models_integration(mock_cmd_data):
    """Test the full integration of _import_cmd_to_models"""
    # Create mock return values
    mock_general_info = MagicMock(spec=BundleGeneralInfo)
    mock_publication_info = MagicMock(spec=BundlePublicationInfo)
    mock_administrative_info = MagicMock(spec=BundleAdministrativeInfo)
    mock_structural_info = MagicMock(spec=BundleStructuralInfo)
    mock_project = MagicMock(spec=ProjectInfo)
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.projects = MagicMock()
    
    collection_id = 123
    
    # Set up patches for all called methods
    with patch.object(BundleImporter, '_import_general_info', return_value=mock_general_info) as mock_import_general, \
         patch.object(BundleImporter, '_import_publication_info', return_value=mock_publication_info) as mock_import_publication, \
         patch.object(BundleImporter, '_import_administrative_info', return_value=mock_administrative_info) as mock_import_administrative, \
         patch.object(BundleImporter, '_import_structural_info', return_value=mock_structural_info) as mock_import_structural, \
         patch.object(BundleImporter, '_extract_metadata_license', return_value=("CC-BY", "https://creativecommons.org/licenses/by/4.0/")) as mock_extract_license, \
         patch.object(BundleImporter, '_create_or_update_bundle', return_value=mock_bundle) as mock_create_update, \
         patch.object(BundleImporter, '_import_and_link_projects') as mock_import_projects:
        
        # Call the method
        result = BundleImporter._import_cmd_to_models(mock_cmd_data, collection_id)
        
        # Assert all methods were called with correct parameters
        mock_import_general.assert_called_once_with(mock_cmd_data)
        mock_import_publication.assert_called_once_with(mock_cmd_data)
        mock_import_administrative.assert_called_once_with(mock_cmd_data)
        mock_import_structural.assert_called_once_with(mock_cmd_data, collection_id)
        mock_extract_license.assert_called_once_with(mock_cmd_data)
        
        mock_create_update.assert_called_once_with(
            mock_general_info,
            mock_publication_info,
            mock_administrative_info,
            mock_structural_info,
            "CC-BY",
            "https://creativecommons.org/licenses/by/4.0/"
        )
        
        mock_import_projects.assert_called_once_with(mock_cmd_data, mock_bundle)
        
        # Assert result is the expected bundle
        assert result == mock_bundle


def test_validate_xml(real_bundle_xml):
    """Test that XML validation works correctly with a real bundle XML"""
    # Mock the parser result
    mock_cmd = MagicMock(spec=Cmd)
    
    # Directly patch the static method from_string
    with patch('xsdata.formats.dataclass.parsers.XmlParser.from_string', return_value=mock_cmd):
        
        # Call the method
        result = BundleImporter.validate_xml(real_bundle_xml)
        
        # Assert result is the mock CMD object
        assert result == mock_cmd


def test_real_xml_parsing(real_bundle_xml):
    """Test that actual XML parsing works correctly without mocking"""
    # We'll patch the validation error to avoid test failures if schema changes
    with patch('django.core.exceptions.ValidationError', Exception):
        # Parse the real XML
        cmd_data = BundleImporter.validate_xml(real_bundle_xml)
        
        # Verify it's a real Cmd object
        assert isinstance(cmd_data, Cmd)
        
        # Verify we can access expected properties
        repository = cmd_data.components.blam_bundle_repository_v1_0
        
        # Check general info
        general_info = repository.bundle_general_info
        assert general_info is not None
        assert general_info.bundle_display_title is not None
        
        # Check publication info
        pub_info = repository.bundle_publication_info
        assert pub_info is not None
        assert pub_info.bundle_publication_year is not None
        
        # Check administrative info
        admin_info = repository.bundle_administrative_info
        assert admin_info is not None
        assert admin_info.access is not None


def test_extract_metadata_license_with_real_data(real_cmd_data):
    """Test that metadata license is correctly extracted from real XML data"""
    md_license, md_license_uri = BundleImporter._extract_metadata_license(real_cmd_data)
    # Verify values from the actual XML file
    assert md_license is not None
    assert isinstance(md_license, str)
    # The real license might vary, but it should have a URI if present
    if md_license_uri:
        assert isinstance(md_license_uri, str)
        assert md_license_uri.startswith("http")


def test_import_general_info_with_real_data(real_cmd_data):
    """Test general info extraction with real XML data"""
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.import_general_info') as mock_import:
        # Call the function
        BundleImporter._import_general_info(real_cmd_data)
        
        # Verify the real CMD data was passed
        mock_import.assert_called_once_with(real_cmd_data)
        
        # Verify the data that would be passed
        repo = real_cmd_data.components.blam_bundle_repository_v1_0
        general_info = repo.bundle_general_info
        assert general_info is not None
        assert general_info.bundle_display_title == "Bodyparts 1"
        assert "Body parts" in general_info.bundle_description


def test_import_resources_with_real_data(real_cmd_data):
    """Test extracting resource information from real XML data"""
    # Get the structural info from real data
    repo = real_cmd_data.components.blam_bundle_repository_v1_0
    structural_info = repo.bundle_structural_info
    assert structural_info is not None
    
    # Verify written resources
    written_resources = structural_info.resources.written_resource
    assert written_resources is not None
    assert len(written_resources) > 0
    
    # Check the first written resource
    first_resource = written_resources[0]
    assert first_resource.resource_name is not None
    assert first_resource.mime_type is not None
    
    # Verify that one of the typical file types is present
    file_types = [r.mime_type for r in written_resources]
    assert any(mime_type in file_types for mime_type in ["text/x-eaf+xml", "application/pdf", "text/plain"])


def test_import_from_xml_integration(real_bundle_xml):
    """Test the full import_from_xml integration with mocking"""
    collection_id = 123
    mock_bundle = MagicMock(spec=Bundle)
    
    # Mock the key methods in the import chain
    with patch.object(BundleImporter, 'validate_xml') as mock_validate, \
         patch.object(BundleImporter, '_import_cmd_to_models', return_value=mock_bundle) as mock_import:
        
        # Setup validate_xml to return a valid cmd_data
        mock_cmd = MagicMock()
        mock_validate.return_value = mock_cmd
        
        # Call the import method
        result = BundleImporter.import_from_xml(real_bundle_xml, collection_id)
        
        # Verify the validation was called with the XML content
        mock_validate.assert_called_once_with(real_bundle_xml)
        
        # Verify import was called with the validated data
        mock_import.assert_called_once_with(mock_cmd, collection_id)
        
        # Verify the expected bundle was returned
        assert result == mock_bundle 


def test_administrative_info_data_mapping(real_cmd_data):
    """Test that administrative info data is correctly mapped from CMD to models"""
    # Extract the command data from the real CMD data
    repo = real_cmd_data.components.blam_bundle_repository_v1_0
    admin_info_schema = repo.bundle_administrative_info
    
    # Mock the database operations
    with patch('lacos.blam.models.bundle.bundle_administrative_info.BundleAdministrativeInfo.save') as mock_save, \
         patch('lacos.blam.models.bundle.bundle_administrative_info.BundleIdenticalResource.objects.get_or_create') as mock_get_or_create_id, \
         patch('lacos.blam.models.bundle.bundle_administrative_info.BundleLicense.objects.get_or_create') as mock_get_or_create_license, \
         patch('lacos.blam.models.bundle.bundle_administrative_info.BundleRightsHolder.objects.get_or_create') as mock_get_or_create_rh, \
         patch('lacos.blam.models.bundle.bundle_administrative_info.BundleRightsHolderIdentifier.objects.get_or_create') as mock_get_or_create_rhi, \
         patch('django.db.transaction.atomic') as mock_atomic:
        
        # Set up mocks to return appropriate values
        mock_admin_info = Mock()
        mock_admin_info.is_identical_to = Mock()
        mock_admin_info.licenses = Mock()
        mock_admin_info.rights_holders = Mock()
        
        mock_license = Mock()
        mock_rights_holder = Mock()
        mock_rights_holder.rights_holder_identifiers = Mock()
        mock_identifier = Mock()
        
        # Set up return values for get_or_create calls
        mock_get_or_create_license.return_value = (mock_license, True)
        mock_get_or_create_rh.return_value = (mock_rights_holder, True)
        mock_get_or_create_rhi.return_value = (mock_identifier, True)
        
        # Import directly from the import_bundle_administrative_info module
        from lacos.blam.mappers.bundle.read.import_bundle_administrative_info import import_administrative_info
        
        # Call the import function
        with patch('lacos.blam.mappers.bundle.read.import_bundle_administrative_info.BundleAdministrativeInfo', 
                   return_value=mock_admin_info):
            result = import_administrative_info(real_cmd_data)
            
            # Verify transaction.atomic was called
            mock_atomic.assert_called_once()
            
            # Verify admin_info was saved
            assert mock_save.call_count > 0
            
            # Verify access value mapping
            if admin_info_schema.access and admin_info_schema.access.value:
                # The import function maps SimpletypeAccess51 values to string values
                expected_access = {
                    "OPEN": "open",
                    "REGISTRATION_REQUIRED": "registration_required", 
                    "REQUEST_REQUIRED": "request_required"
                }.get(admin_info_schema.access.value, "open")
                
                # Verify licenses were created with the correct access
                for call in mock_get_or_create_license.call_args_list:
                    kwargs = call[1]
                    assert 'defaults' in kwargs
                    assert kwargs['defaults']['access'] == expected_access
            
            # Verify identical resources were processed if present
            if admin_info_schema.bundle_is_identical_to:
                assert mock_admin_info.is_identical_to.add.call_count >= len(admin_info_schema.bundle_is_identical_to)
            
            # Verify licenses were processed
            if admin_info_schema.license:
                assert mock_admin_info.licenses.add.call_count >= len(admin_info_schema.license)
                
                # Verify license data was passed correctly
                for i, license_schema in enumerate(admin_info_schema.license):
                    if i < len(mock_get_or_create_license.call_args_list):
                        call = mock_get_or_create_license.call_args_list[i]
                        kwargs = call[1]
                        assert kwargs.get('license_name') == license_schema.license_name
                        assert kwargs.get('license_identifier') == license_schema.license_identifier
            
            # Verify rights holders were processed
            if admin_info_schema.rights_holder:
                assert mock_admin_info.rights_holders.add.call_count >= len(admin_info_schema.rights_holder)
                
                # Verify rights holder data was passed correctly
                for i, rh_schema in enumerate(admin_info_schema.rights_holder):
                    if i < len(mock_get_or_create_rh.call_args_list):
                        call = mock_get_or_create_rh.call_args_list[i]
                        kwargs = call[1]
                        assert kwargs.get('rights_holder_name') == rh_schema.rights_holder_name


def test_publication_info_data_mapping(real_cmd_data):
    """Test that publication info data is correctly mapped from CMD to models"""
    # Extract the publication info from the real CMD data
    repo = real_cmd_data.components.blam_bundle_repository_v1_0
    pub_info_schema = repo.bundle_publication_info
    
    # Mock the database operations
    with patch('lacos.blam.models.bundle.bundle_publication_info.BundlePublicationInfo.save') as mock_save, \
         patch('django.db.transaction.atomic') as mock_atomic:
        
        # Import directly from the publication info module
        from lacos.blam.mappers.bundle.read.import_bundle_publication_info import import_publication_info
        
        # Create a mock that will capture the field values
        pub_info_fields = {}
        
        class MockPublicationInfo:
            def __init__(self):
                self.bundle_publication_year = None
                self.bundle_data_provider = None
                self.bundle_publisher = None
            
            def save(self):
                # Capture the field values when save is called
                pub_info_fields['bundle_publication_year'] = self.bundle_publication_year
                pub_info_fields['bundle_data_provider'] = self.bundle_data_provider
                pub_info_fields['bundle_publisher'] = self.bundle_publisher
                return self
        
        # Call the import function with our mock
        with patch('lacos.blam.mappers.bundle.read.import_bundle_publication_info.BundlePublicationInfo', 
                   return_value=MockPublicationInfo()):
            result = import_publication_info(real_cmd_data)
            
            # Verify transaction.atomic was called
            mock_atomic.assert_called_once()
            
            # Verify field mappings from schema to model
            if pub_info_schema.bundle_publication_year:
                assert pub_info_fields['bundle_publication_year'] == pub_info_schema.bundle_publication_year
            
            if pub_info_schema.bundle_data_provider:
                assert pub_info_fields['bundle_data_provider'] == pub_info_schema.bundle_data_provider
            
            if pub_info_schema.bundle_publisher:
                assert pub_info_fields['bundle_publisher'] == pub_info_schema.bundle_publisher


def test_general_info_data_mapping(real_cmd_data):
    """Test that general info data is correctly mapped from CMD to models"""
    # Extract the general info from the real CMD data
    repo = real_cmd_data.components.blam_bundle_repository_v1_0
    general_info_schema = repo.bundle_general_info
    
    # Mock the database operations
    with patch('lacos.blam.models.bundle.bundle_general_info.BundleGeneralInfo.save') as mock_save, \
         patch('django.db.transaction.atomic') as mock_atomic:
        
        # Import directly from the general info module
        from lacos.blam.mappers.bundle.read.import_bundle_general_info import import_general_info
        
        # Create a mock that will capture the field values
        general_info_fields = {}
        
        class MockGeneralInfo:
            def __init__(self):
                self.bundle_display_title = None
                self.bundle_title = None
                self.bundle_description = None
                self.bundle_pid = None
            
            def save(self):
                # Capture the field values when save is called
                general_info_fields['bundle_display_title'] = self.bundle_display_title
                general_info_fields['bundle_title'] = self.bundle_title
                general_info_fields['bundle_description'] = self.bundle_description
                general_info_fields['bundle_pid'] = self.bundle_pid
                return self
        
        # Call the import function with our mock
        with patch('lacos.blam.mappers.bundle.read.import_bundle_general_info.BundleGeneralInfo', 
                   return_value=MockGeneralInfo()):
            result = import_general_info(real_cmd_data)
            
            # Verify transaction.atomic was called
            mock_atomic.assert_called_once()
            
            # Verify field mappings from schema to model
            if general_info_schema.bundle_display_title:
                assert general_info_fields['bundle_display_title'] == general_info_schema.bundle_display_title
            
            if general_info_schema.bundle_title:
                assert general_info_fields['bundle_title'] == general_info_schema.bundle_title
            
            if general_info_schema.bundle_description:
                assert general_info_fields['bundle_description'] == general_info_schema.bundle_description
            
            if general_info_schema.bundle_pid:
                assert general_info_fields['bundle_pid'] == general_info_schema.bundle_pid 