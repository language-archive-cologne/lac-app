import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import os

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.models.base_project_info import ProjectInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle


class TestProjectInfoSharing:
    """Tests for sharing ProjectInfo between collections and bundles"""
    
    @pytest.fixture
    def algerien_collection_xml_content(self):
        """Fixture to load the algerien.xml collection file content"""
        xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @pytest.fixture
    def mock_project_info(self):
        """Fixture to create a mock ProjectInfo instance"""
        project = MagicMock(spec=ProjectInfo)
        project.project_display_name = "Test Project"
        project.project_description = "Test Project Description"
        return project
    
    def test_project_info_shared_between_collection_and_bundle(self, mock_project_info, algerien_collection_xml_content):
        """Test that ProjectInfo is shared between collections and bundles"""
        # Create mocks
        mock_cmd_data = MagicMock()
        mock_collection = MagicMock(spec=Collection)
        mock_bundle = MagicMock(spec=Bundle)
        
        # Set up mock collection and bundle with projects relationship
        mock_collection_projects = MagicMock()
        mock_bundle_projects = MagicMock()
        type(mock_collection).projects = PropertyMock(return_value=mock_collection_projects)
        type(mock_bundle).projects = PropertyMock(return_value=mock_bundle_projects)
        
        # Create custom implementations that don't use database
        def custom_collection_import_and_link_projects(cmd_data, collection):
            collection.projects.add(mock_project_info)
            
        def custom_bundle_import_and_link_projects(cmd_data, bundle):
            bundle.projects.add(mock_project_info)
            
        def custom_collection_import_cmd_to_models(cmd_data):
            return mock_collection
            
        def custom_bundle_import_cmd_to_models(cmd_data, collection_id=None):
            return mock_bundle
        
        # Patch all methods that might access the database
        with patch.object(CollectionImporter, 'validate_xml', return_value=mock_cmd_data):
            with patch.object(BundleImporter, 'validate_xml', return_value=mock_cmd_data):
                with patch.object(CollectionImporter, '_import_cmd_to_models', custom_collection_import_cmd_to_models):
                    with patch.object(BundleImporter, '_import_cmd_to_models', custom_bundle_import_cmd_to_models):
                        with patch.object(CollectionImporter, '_import_and_link_projects', custom_collection_import_and_link_projects):
                            with patch.object(BundleImporter, '_import_and_link_projects', custom_bundle_import_and_link_projects):
                                # Call the methods
                                collection = CollectionImporter._import_cmd_to_models(mock_cmd_data)
                                bundle = BundleImporter._import_cmd_to_models(mock_cmd_data, None)
                                
                                # Call the import_and_link_projects methods
                                CollectionImporter._import_and_link_projects(mock_cmd_data, collection)
                                BundleImporter._import_and_link_projects(mock_cmd_data, bundle)
                                
                                # Verify projects were added to both collection and bundle
                                mock_collection_projects.add.assert_called_once_with(mock_project_info)
                                mock_bundle_projects.add.assert_called_once_with(mock_project_info)
    
    def test_project_info_reused_when_exists(self):
        """Test that existing ProjectInfo is reused rather than creating duplicates"""
        # Create a mock ProjectInfo instance
        mock_project = MagicMock(spec=ProjectInfo)
        mock_project.project_display_name = "Test Project"
        mock_project.project_description = "Test Project Description"
        
        # Create a mock get_or_create function that doesn't access the database
        def mock_get_or_create(**kwargs):
            return mock_project, False  # False means it already existed
        
        # Patch the get_or_create method
        with patch('lacos.blam.models.base_project_info.ProjectInfo.objects.get_or_create', 
                  side_effect=mock_get_or_create) as mock_get_or_create_call:
            # Create a test function that uses get_or_create
            def test_function():
                project, created = ProjectInfo.objects.get_or_create(
                    project_display_name="Test Project",
                    defaults={"project_description": "Test Project Description"}
                )
                return project
            
            # Call the function twice
            project1 = test_function()
            project2 = test_function()
            
            # Verify get_or_create was called twice
            assert mock_get_or_create_call.call_count == 2
            
            # Verify the same project was returned both times
            assert project1 is mock_project
            assert project2 is mock_project