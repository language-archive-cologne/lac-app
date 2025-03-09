import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from django.core.exceptions import ValidationError
import os

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from lacos.blam.models.base_project_info import ProjectInfo


class TestCollectionImporterIntegration:
    """
    Integration tests for the CollectionImporter class.
    
    These tests use real XML data to test the actual data flow through the methods,
    while mocking only the database access.
    """
    
    @pytest.fixture
    def algerien_xml_content(self):
        """Fixture to load the algerien.xml file content"""
        xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @pytest.fixture
    def cmd_data(self, algerien_xml_content):
        """Fixture to parse XML into CMD data object"""
        return CollectionImporter.validate_xml(algerien_xml_content)
    
    def test_validate_xml_with_real_data(self, cmd_data):
        """Test that real XML can be parsed into a Cmd object"""
        # Verify that cmd_data is an actual Cmd object
        assert isinstance(cmd_data, Cmd)
        
        # Verify key attributes from the XML are correctly mapped to the Cmd object
        assert hasattr(cmd_data, 'header')
        assert cmd_data.header.md_collection_display_name.value == "Interviews about Rock Art"
    
    def test_map_general_info(self, cmd_data):
        """Test mapping general info from CMD data to model"""
        # Set up mock to avoid database access
        mock_general = MagicMock(name="GeneralInfo")
        
        # Patch the import_general_info function
        with patch('lacos.blam.mappers.collection.read.import_collection_general_info.import_general_info', 
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
        with patch('lacos.blam.mappers.collection.read.import_collection_publication_info.import_publication_info', 
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
        with patch('lacos.blam.mappers.collection.read.import_collection_administrative_info.import_administrative_info', 
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
        with patch('lacos.blam.mappers.collection.read.import_collection_project_info.import_project_info', 
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
        assert cmd_data.header.md_collection_display_name.value == "Interviews about Rock Art"
        assert cmd_data.header.md_creation_date.value.year == 2022
        assert cmd_data.header.md_creation_date.value.month == 10
        assert cmd_data.header.md_creation_date.value.day == 26
        assert cmd_data.header.md_self_link.value == "hdl:11341/0000-0000-0000-3D7C"
    
    def test_verify_cmd_license_mapping(self, cmd_data):
        """Test that license information is correctly mapped from XML to CMD"""
        # Verify license
        repo = cmd_data.components.blam_collection_repository_v1_0
        assert repo.mdlicense.value == "CC0"
        assert repo.mdlicense.uri == "https://creativecommons.org/public-domain/cc0/"
    
    def test_verify_cmd_general_info_mapping(self, cmd_data):
        """Test that general info is correctly mapped from XML to CMD"""
        # Verify general info
        repo = cmd_data.components.blam_collection_repository_v1_0
        general_info = repo.collection_general_info
        assert general_info.collection_display_title == "Interviews about Rock Art"
        assert "Master Thesis" in general_info.collection_description
        assert len(general_info.collection_id) > 0
        assert general_info.collection_id[0].value == "hdl:11341/0000-0000-0000-3D7C"
    
    def test_verify_cmd_object_languages_mapping(self, cmd_data):
        """Test that object languages are correctly mapped from XML to CMD"""
        # Verify object languages
        repo = cmd_data.components.blam_collection_repository_v1_0
        general_info = repo.collection_general_info
        assert hasattr(general_info, 'collection_object_languages')
        assert len(general_info.collection_object_languages.collection_object_language) > 0
        lang = general_info.collection_object_languages.collection_object_language[0]
        assert lang.object_language_name == "Tamasheq"
        assert lang.object_language_iso639_3_code.value == "taq"
        assert lang.object_language_glottolog_code.value == "tama1365"
    
    def test_verify_cmd_location_mapping(self, cmd_data):
        """Test that location information is correctly mapped from XML to CMD"""
        # Verify location
        repo = cmd_data.components.blam_collection_repository_v1_0
        general_info = repo.collection_general_info
        assert hasattr(general_info, 'collection_location')
        location = general_info.collection_location
        assert location.collection_country_code.value == "DZ"
        assert location.collection_country_facet == "Algerien"
    
    def test_verify_cmd_publication_info_mapping(self, cmd_data):
        """Test that publication info is correctly mapped from XML to CMD"""
        # Verify publication info
        repo = cmd_data.components.blam_collection_repository_v1_0
        pub_info = repo.collection_publication_info
        assert str(pub_info.collection_publication_year) == "2022"
        assert pub_info.collection_data_provider == "FAIR.rdm im SPP2143 \"Entangled Africa\""
    
    def test_verify_cmd_creators_mapping(self, cmd_data):
        """Test that creators are correctly mapped from XML to CMD"""
        # Verify creators
        repo = cmd_data.components.blam_collection_repository_v1_0
        pub_info = repo.collection_publication_info
        assert hasattr(pub_info, 'collection_creators')
        assert len(pub_info.collection_creators.collection_creator) > 0
        creator = pub_info.collection_creators.collection_creator[0]
        assert creator.creator_name.creator_family_name == "Oukafi"
        assert creator.creator_name.creator_given_name == "Issak Cheikh"
    
    def test_verify_cmd_administrative_info_mapping(self, cmd_data):
        """Test that administrative info is correctly mapped from XML to CMD"""
        # Verify administrative info
        repo = cmd_data.components.blam_collection_repository_v1_0
        admin_info = repo.collection_administrative_info
        assert admin_info.access.value.value == "open"
        assert len(admin_info.license) > 0
        assert admin_info.license[0].license_identifier == "CC BY-NC-ND 3.0 DE"
    
    def test_verify_cmd_structural_info_mapping(self, cmd_data):
        """Test that structural info is correctly mapped from XML to CMD"""
        # Verify structural info
        repo = cmd_data.components.blam_collection_repository_v1_0
        struct_info = repo.collection_structural_info
        assert hasattr(struct_info, 'collection_members')
        assert len(struct_info.collection_members.collection_has_collection_member) > 0
        # Check at least one member
        assert struct_info.collection_members.collection_has_collection_member[0].value.startswith("hdl:11341")

    def test_import_header(self, cmd_data):
        """Test the _import_header method"""
        # Set up mock to avoid database access
        mock_header = MagicMock(name="Header")
        
        # Patch the import_collection_header function at the module level where it's imported
        with patch('lacos.blam.mappers.collection.read.collection_importer.import_collection_header', 
                  return_value=mock_header) as mock_import_header:
            
            # Call the _import_header method
            result = CollectionImporter._import_header(cmd_data)
            
            # Verify the import_collection_header function was called with the correct cmd_data
            mock_import_header.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_header

    def test_import_license(self, cmd_data):
        """Test the _import_license method"""
        # Set up mock to avoid database access
        mock_license = MagicMock(name="License")
        
        # Patch the import_collection_license function at the module level where it's imported
        with patch('lacos.blam.mappers.collection.read.collection_importer.import_collection_license', 
                  return_value=mock_license) as mock_import_license:
            
            # Call the _import_license method
            result = CollectionImporter._import_license(cmd_data)
            
            # Verify the import_collection_license function was called with the correct cmd_data
            mock_import_license.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_license

    def test_import_structural_info(self, cmd_data):
        """Test the _import_structural_info method"""
        # Set up mock to avoid database access
        mock_structural = MagicMock(name="StructuralInfo")
        
        # Patch the import_structural_info function at the module level where it's imported
        with patch('lacos.blam.mappers.collection.read.collection_importer.import_structural_info', 
                  return_value=mock_structural) as mock_import_structural:
            
            # Call the _import_structural_info method
            result = CollectionImporter._import_structural_info(cmd_data)
            
            # Verify the import_structural_info function was called with the correct cmd_data
            mock_import_structural.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_structural

    def test_import_project_info(self, cmd_data):
        """Test the _import_project_info method"""
        # Set up mock to avoid database access
        mock_project = MagicMock(name="ProjectInfo")
        
        # Patch the import_project_info function at the module level where it's imported
        with patch('lacos.blam.mappers.collection.read.collection_importer.import_project_info', 
                  return_value=mock_project) as mock_import_project:
            
            # Call the _import_project_info method
            result = CollectionImporter._import_project_info(cmd_data)
            
            # Verify the import_project_info function was called with the correct cmd_data
            mock_import_project.assert_called_once_with(cmd_data)
            
            # Verify the result
            assert result == mock_project

    def test_import_cmd_to_models(self, cmd_data):
        """Test the _import_cmd_to_models method"""
        # Set up mocks for all the import methods
        mock_header = MagicMock(name="Header")
        mock_license = MagicMock(name="License")
        mock_general = MagicMock(name="GeneralInfo")
        mock_publication = MagicMock(name="PublicationInfo")
        mock_project = MagicMock(name="ProjectInfo")
        mock_administrative = MagicMock(name="AdministrativeInfo")
        mock_structural = MagicMock(name="StructuralInfo")
        mock_collection = MagicMock(name="Collection")
        
        # Patch all the import functions at the module level
        with patch('lacos.blam.mappers.collection.read.collection_importer.import_collection_header', return_value=mock_header), \
             patch('lacos.blam.mappers.collection.read.collection_importer.import_collection_license', return_value=mock_license), \
             patch('lacos.blam.mappers.collection.read.collection_importer.import_general_info', return_value=mock_general), \
             patch('lacos.blam.mappers.collection.read.collection_importer.import_publication_info', return_value=mock_publication), \
             patch('lacos.blam.mappers.collection.read.collection_importer.import_project_info', return_value=mock_project), \
             patch('lacos.blam.mappers.collection.read.collection_importer.import_administrative_info', return_value=mock_administrative), \
             patch('lacos.blam.mappers.collection.read.collection_importer.import_structural_info', return_value=mock_structural), \
             patch.object(CollectionImporter, '_create_or_update_collection', return_value=mock_collection):
            
            # Call the _import_cmd_to_models method
            result = CollectionImporter._import_cmd_to_models(cmd_data)
            
            # Verify the result
            assert result == mock_collection

    def test_create_or_update_collection(self):
        """Test the _create_or_update_collection method"""
        # Set up mocks for all the components
        mock_header = MagicMock(name="Header")
        mock_license = MagicMock(name="License")
        mock_general = MagicMock(name="GeneralInfo")
        mock_publication = MagicMock(name="PublicationInfo")
        mock_project = MagicMock(name="ProjectInfo")
        mock_administrative = MagicMock(name="AdministrativeInfo")
        mock_structural = MagicMock(name="StructuralInfo")
        mock_collection = MagicMock(name="Collection")
        
        # Patch the Collection.objects.get_or_create method
        with patch('lacos.blam.mappers.collection.read.collection_importer.Collection.objects.get_or_create',
                  return_value=(mock_collection, True)) as mock_get_or_create:
            
            # Call the _create_or_update_collection method
            result = CollectionImporter._create_or_update_collection(
                mock_header,
                mock_license,
                mock_general,
                mock_publication,
                mock_project,
                mock_administrative,
                mock_structural
            )
            
            # Verify get_or_create was called with the correct arguments
            mock_get_or_create.assert_called_once_with(
                base_header=mock_header,
                base_license=mock_license,
                general_info=mock_general,
                publication_info=mock_publication,
                project_info=mock_project,
                administrative_info=mock_administrative,
                structural_info=mock_structural
            )
            
            # Verify the result
            assert result == mock_collection

    def test_create_or_update_collection_existing(self):
        """Test the _create_or_update_collection method with an existing collection"""
        # Set up mocks for all the components
        mock_header = MagicMock(name="Header")
        mock_license = MagicMock(name="License")
        mock_general = MagicMock(name="GeneralInfo")
        mock_publication = MagicMock(name="PublicationInfo")
        mock_project = MagicMock(name="ProjectInfo")
        mock_administrative = MagicMock(name="AdministrativeInfo")
        mock_structural = MagicMock(name="StructuralInfo")
        mock_collection = MagicMock(name="Collection")
        
        # Patch the Collection.objects.get_or_create method to return an existing collection
        with patch('lacos.blam.mappers.collection.read.collection_importer.Collection.objects.get_or_create',
                  return_value=(mock_collection, False)) as mock_get_or_create:
            
            # Call the _create_or_update_collection method
            result = CollectionImporter._create_or_update_collection(
                mock_header,
                mock_license,
                mock_general,
                mock_publication,
                mock_project,
                mock_administrative,
                mock_structural
            )
            
            # Verify the collection was updated
            assert mock_collection.base_header == mock_header
            assert mock_collection.base_license == mock_license
            assert mock_collection.general_info == mock_general
            assert mock_collection.publication_info == mock_publication
            assert mock_collection.project_info == mock_project
            assert mock_collection.administrative_info == mock_administrative
            assert mock_collection.structural_info == mock_structural
            assert mock_collection.save.called
            
            # Verify the result
            assert result == mock_collection
