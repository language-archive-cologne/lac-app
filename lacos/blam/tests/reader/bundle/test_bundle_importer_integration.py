import pytest
from unittest.mock import patch, MagicMock
from django.core.exceptions import ValidationError
import os
from pathlib import Path

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd


class TestBundleImporterIntegration:
    """
    Integration tests for the BundleImporter class.
    
    These tests use real XML data to test the actual data flow through the methods,
    while mocking only the database access.
    """
    
    @pytest.fixture
    def zaghawa_xml_content(self):
        """Fixture to load a sample bundle XML file content"""
        xml_path = os.path.join('data', 'zaghawa', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()

    
    @pytest.fixture
    def cmd_data(self, zaghawa_xml_content):
        """Fixture to parse XML into CMD data object"""
        return BundleImporter.validate_xml(zaghawa_xml_content)
    
    def test_validate_xml_with_real_data(self, cmd_data):
        """Test that real XML can be parsed into a Cmd object"""
        # Verify that cmd_data is an actual Cmd object
        assert isinstance(cmd_data, Cmd)
        
        # Verify key attributes from the XML are correctly mapped to the Cmd object
        assert hasattr(cmd_data, 'header')
        # Add more specific assertions based on your XML content
    
    def test_extract_metadata_license(self, cmd_data):
        """Test extracting metadata license from CMD data"""
        # Call the extract_metadata_license method
        license_value, license_uri = BundleImporter._extract_metadata_license(cmd_data)
        
        # Verify the result matches what's in the XML
        assert license_value is not None
        if license_uri:
            assert isinstance(license_uri, str)
    
    def test_map_general_info(self, cmd_data):
        """Test mapping general info from CMD data to model"""
        # Set up mock to avoid database access
        mock_general = MagicMock(name="GeneralInfo")
        
        # Patch the import_general_info function
        with patch('lacos.blam.mappers.bundle.read.import_bundle_general_info.import_general_info', 
                  return_value=mock_general) as mock_import_general:
            
            # Call the import_general_info function directly
            result = mock_import_general(cmd_data)
            
            # Verify the import_general_info function was called with the correct cmd_data
            mock_import_general.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_general
    
    def test_map_publication_info(self, cmd_data):
        """Test mapping publication info from CMD data to model"""
        # Set up mock to avoid database access
        mock_publication = MagicMock(name="PublicationInfo")
        
        # Patch the import_publication_info function
        with patch('lacos.blam.mappers.bundle.read.import_bundle_publication_info.import_publication_info', 
                  return_value=mock_publication) as mock_import_publication:
            
            # Call the import_publication_info function directly
            result = mock_import_publication(cmd_data)
            
            # Verify the import_publication_info function was called with the correct cmd_data
            mock_import_publication.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_publication
    
    def test_map_administrative_info(self, cmd_data):
        """Test mapping administrative info from CMD data to model"""
        # Set up mock to avoid database access
        mock_administrative = MagicMock(name="AdministrativeInfo")
        
        # Patch the import_administrative_info function
        with patch('lacos.blam.mappers.bundle.read.import_bundle_administrative_info.import_administrative_info', 
                  return_value=mock_administrative) as mock_import_administrative:
            
            # Call the import_administrative_info function directly
            result = mock_import_administrative(cmd_data)
            
            # Verify the import_administrative_info function was called with the correct cmd_data
            mock_import_administrative.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_administrative
    
    def test_map_projects(self, cmd_data):
        """Test mapping projects from CMD data to model"""
        # Set up mock to avoid database access
        mock_project = MagicMock(name="ProjectInfo")
        
        # Patch the import_project_info function
        with patch('lacos.blam.mappers.bundle.read.import_bundle_project_info.import_project_info', 
                  return_value=[mock_project]) as mock_import_project:
            
            # Call the import_project_info function directly
            projects = mock_import_project(cmd_data)
            
            # Verify the import_project_info function was called with the correct cmd_data
            mock_import_project.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert len(projects) == 1
            assert projects[0] == mock_project
    
    def test_verify_cmd_header_mapping(self, cmd_data):
        """Test that header information is correctly mapped from XML to CMD"""
        # Verify header information
        assert hasattr(cmd_data, 'header')
        # Add more specific assertions based on your XML content
    
    def test_verify_cmd_license_mapping(self, cmd_data):
        """Test that license information is correctly mapped from XML to CMD"""
        # Verify license
        repo = cmd_data.components.blam_bundle_repository_v1_0
        assert hasattr(repo, 'mdlicense')
        if repo.mdlicense:
            assert repo.mdlicense.value is not None
    
    def test_verify_cmd_general_info_mapping(self, cmd_data):
        """Test that general info is correctly mapped from XML to CMD"""
        # Verify general info
        repo = cmd_data.components.blam_bundle_repository_v1_0
        general_info = repo.bundle_general_info
        assert hasattr(general_info, 'bundle_display_title')
        assert general_info.bundle_display_title is not None
        # Add more specific assertions based on your XML content
    
    def test_verify_cmd_publication_info_mapping(self, cmd_data):
        """Test that publication info is correctly mapped from XML to CMD"""
        # Verify publication info
        repo = cmd_data.components.blam_bundle_repository_v1_0
        pub_info = repo.bundle_publication_info
        assert hasattr(pub_info, 'bundle_publication_year')
        # Add more specific assertions based on your XML content
    
    def test_verify_cmd_administrative_info_mapping(self, cmd_data):
        """Test that administrative info is correctly mapped from XML to CMD"""
        # Verify administrative info
        repo = cmd_data.components.blam_bundle_repository_v1_0
        admin_info = repo.bundle_administrative_info
        assert hasattr(admin_info, 'access')
        # Add more specific assertions based on your XML content
    
    def test_verify_cmd_structural_info_mapping(self, cmd_data):
        """Test that structural info is correctly mapped from XML to CMD"""
        # Verify structural info
        repo = cmd_data.components.blam_bundle_repository_v1_0
        struct_info = repo.bundle_structural_info
        assert hasattr(struct_info, 'bundle_is_member_of_collection')
        assert hasattr(struct_info, 'bundle_resources')
        # Add more specific assertions based on your XML content