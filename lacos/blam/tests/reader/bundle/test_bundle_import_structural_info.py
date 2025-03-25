import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from django.core.exceptions import ObjectDoesNotExist

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.mappers.bundle.read.import_bundle_structural_info import (
    import_structural_info, 
    import_additional_metadata_files,
    import_bundle_resources,
    import_media_resources,
    import_written_resources,
    import_other_resources
)
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleAdditionalMetadataFile,
    BundleResources,
    MediaResource,
    WrittenResource,
    WrittenResourceAnnotation,
    OtherResource
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices


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


@pytest.fixture
def mock_collection():
    """Create a mock collection for testing without database operations."""
    # Create a mock instead of real database objects
    mock_collection = MagicMock(spec=Collection)
    
    # Create mock for general_info with the expected identifier
    mock_general_info = MagicMock()
    mock_general_info.id_value = "hdl:11341/00-0000-0000-0000-1AC6-9"
    mock_general_info.id_type = "Handle"
    mock_general_info.display_title = "Zaghawa Collection"
    
    # Set up the general_info property
    type(mock_collection).general_info = PropertyMock(return_value=mock_general_info)
    
    return mock_collection


@pytest.mark.django_db
def test_cmd_structural_data_parsing(real_cmd_data):
    """Test that structural data is correctly parsed from XML"""
    # Get the structural info from CMD data
    components = real_cmd_data.components
    structural_info = components.blam_bundle_repository_v1_0.bundle_structural_info
    
    # Verify structural info exists
    assert structural_info is not None
    
    # Check is_member_of_collection (matches real XML data)
    assert hasattr(structural_info, 'bundle_is_member_of_collection')
    assert structural_info.bundle_is_member_of_collection is not None
    assert hasattr(structural_info.bundle_is_member_of_collection, 'value')
    assert structural_info.bundle_is_member_of_collection.value == "hdl:11341/00-0000-0000-0000-1AC6-9"
    assert hasattr(structural_info.bundle_is_member_of_collection, 'identifier_type')
    assert structural_info.bundle_is_member_of_collection.identifier_type.value == "Handle"
    
    # Check bundle_resources
    assert hasattr(structural_info, 'bundle_resources')
    assert structural_info.bundle_resources is not None
    
    # Check media resources from real XML
    resources = structural_info.bundle_resources
    assert hasattr(resources, 'media_resource')
    assert resources.media_resource is not None
    assert len(resources.media_resource) == 1
    
    media = resources.media_resource[0]
    assert media.file_name == "ZAG_EOI_20141009_1.wav"
    assert media.file_pid == "hdl:11341/00-0000-0000-0000-1B28-A"
    assert media.mime_type == "audio/x-wav"
    assert media.file_length == "1130.3"
    
    # Check written resources from real XML
    assert hasattr(resources, 'written_resource')
    assert resources.written_resource is not None
    assert len(resources.written_resource) == 1
    
    written = resources.written_resource[0]
    assert written.file_name == "ZAG_EOI_20141009_1.eaf"
    assert written.file_pid == "hdl:11341/00-0000-0000-0000-1B29-8"
    assert written.mime_type == "text/x-eaf+xml"
    
    # XML doesn't have other resources
    if hasattr(resources, 'other_resource'):
        assert resources.other_resource is None or len(resources.other_resource) == 0


@pytest.mark.django_db
def test_structural_info_data_mapping(real_cmd_data, mock_collection):
    """Test that structural info is mapped correctly from CMD to Django models"""
    # Get the collection identifier from the XML
    components = real_cmd_data.components
    structural_info = components.blam_bundle_repository_v1_0.bundle_structural_info
    collection_id = structural_info.bundle_is_member_of_collection.value
    
    # Verify the mock collection matches what we expect
    assert mock_collection.general_info.id_value == "hdl:11341/00-0000-0000-0000-1AC6-9"
    assert mock_collection.general_info.id_type == "Handle"
    
    # Patch the get method to return our mock collection
    with patch('lacos.blam.models.collection.collection_general_info.CollectionGeneralInfo.objects.get') as mock_get:
        mock_get.return_value = mock_collection.general_info
        
        # Also patch Collection.objects.get to return our mock collection
        with patch('lacos.blam.models.collection.collection_repository.Collection.objects.get') as mock_coll_get:
            mock_coll_get.return_value = mock_collection
            
            # Patch BundleStructuralInfo.objects.get_or_create to return a mock
            with patch('lacos.blam.models.bundle.bundle_structural_info.BundleStructuralInfo.objects.get_or_create') as mock_create:
                # Create a mock bundle_struct_info with resources
                bundle_struct_info = MagicMock(spec=BundleStructuralInfo)
                bundle_struct_info.is_member_of_collection = mock_collection
                
                # Create mock resources with media and written resources
                resources = MagicMock(spec=BundleResources)
                
                # Create mock media resources
                media = MagicMock(spec=MediaResource)
                media.file_name = "ZAG_EOI_20141009_1.wav"
                media.file_pid = "hdl:11341/00-0000-0000-0000-1B28-A"
                media.mime_type = "audio/x-wav"
                media.file_length = "1130.3"
                
                # Create mock written resources
                written = MagicMock(spec=WrittenResource)
                written.file_name = "ZAG_EOI_20141009_1.eaf"
                written.file_pid = "hdl:11341/00-0000-0000-0000-1B29-8"
                written.mime_type = "text/x-eaf+xml"
                
                # Set up media and written resources
                media_resources = MagicMock()
                media_resources.count.return_value = 1
                media_resources.first.return_value = media
                
                written_resources = MagicMock()
                written_resources.count.return_value = 1
                written_resources.first.return_value = written
                
                # Attach resources to bundle_struct_info
                resources.bundle_media_resources = media_resources
                resources.bundle_written_resources = written_resources
                bundle_struct_info.resources = resources
                
                # Set up the mock return value for get_or_create
                mock_create.return_value = (bundle_struct_info, True)
                
                # Now patch the import_bundle_resources to avoid DB operations
                with patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_bundle_resources'):
                    # Test import with patched functions
                    result = import_structural_info(real_cmd_data, collection_id, "Handle")
                    
                    # Verify the result matches what we expect
                    assert result is bundle_struct_info
                    assert result.is_member_of_collection == mock_collection


@pytest.mark.django_db
def test_get_or_create_structural_info_behavior(real_cmd_data, mock_collection):
    """Test that importing the same structural data twice doesn't create duplicates"""
    # Get the collection identifier from the XML
    components = real_cmd_data.components
    structural_info = components.blam_bundle_repository_v1_0.bundle_structural_info
    collection_id = structural_info.bundle_is_member_of_collection.value
    
    # Patch the get method to return our mock collection
    with patch('lacos.blam.models.collection.collection_general_info.CollectionGeneralInfo.objects.get') as mock_get:
        mock_get.return_value = mock_collection.general_info
        
        # Also patch Collection.objects.get to return our mock collection
        with patch('lacos.blam.models.collection.collection_repository.Collection.objects.get') as mock_coll_get:
            mock_coll_get.return_value = mock_collection
            
            # Patch BundleStructuralInfo.objects.get_or_create to return a mock
            with patch('lacos.blam.models.bundle.bundle_structural_info.BundleStructuralInfo.objects.get_or_create') as mock_create:
                # Create a mock bundle_struct_info
                bundle_struct_info = MagicMock(spec=BundleStructuralInfo)
                bundle_struct_info.is_member_of_collection = mock_collection
                
                # Set up the mock return value for get_or_create
                # First call will indicate "created=True", second will be "created=False"
                mock_create.side_effect = [(bundle_struct_info, True), (bundle_struct_info, False)]
                
                # Test first import
                with patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_bundle_resources'):
                    # First import
                    struct_info1 = import_structural_info(real_cmd_data, collection_id, "Handle")
                    
                    # Second import with same data should get existing record
                    struct_info2 = import_structural_info(real_cmd_data, collection_id, "Handle")
                    
                    # Should be the same record
                    assert struct_info1 is struct_info2
                    
                    # Verify get_or_create was called twice, first time with created=True, second with created=False
                    assert mock_create.call_count == 2


@pytest.mark.django_db
def test_media_resource_import():
    """Test the media resource import function"""
    # Create a mock bundle resources
    bundle_resources = MagicMock(spec=BundleResources)
    bundle_media_resources = MagicMock()
    bundle_resources.bundle_media_resources = bundle_media_resources
    
    # Create mock media resource data based on real XML
    media_data = MagicMock()
    media_data.file_pid = "hdl:11341/00-0000-0000-0000-1B28-A"
    media_data.file_name = "ZAG_EOI_20141009_1.wav"
    media_data.mime_type = "audio/x-wav"
    media_data.file_length = "1130.3"
    media_data.file_description = None  # XML doesn't have this
    
    # Patch get_or_create to return a mock
    with patch('lacos.blam.models.bundle.bundle_structural_info.MediaResource.objects.get_or_create') as mock_get_or_create:
        # Create a mock media resource
        media_resource = MagicMock(spec=MediaResource)
        media_resource.file_name = media_data.file_name
        media_resource.file_pid = media_data.file_pid
        media_resource.mime_type = media_data.mime_type
        media_resource.file_length = media_data.file_length
        
        # Set up return value
        mock_get_or_create.return_value = (media_resource, True)
        
        # Import media resources
        import_media_resources(bundle_resources, [media_data])
        
        # Verify get_or_create was called with correct parameters
        mock_get_or_create.assert_called_once()
        call_args, call_kwargs = mock_get_or_create.call_args
        assert call_kwargs['file_pid'] == "hdl:11341/00-0000-0000-0000-1B28-A"
        assert call_kwargs['defaults']['file_name'] == "ZAG_EOI_20141009_1.wav"
        assert call_kwargs['defaults']['mime_type'] == "audio/x-wav"
        assert call_kwargs['defaults']['file_length'] == "1130.3"
        
        # Verify add was called with the mock media resource
        bundle_media_resources.add.assert_called_once_with(media_resource)
        
        # Test update logic
        mock_get_or_create.reset_mock()
        bundle_media_resources.add.reset_mock()
        
        # Update the mock to return created=False
        mock_get_or_create.return_value = (media_resource, False)
        
        # Create updated media data
        updated_media_data = MagicMock()
        updated_media_data.file_pid = "hdl:11341/00-0000-0000-0000-1B28-A"
        updated_media_data.file_name = "ZAG_EOI_20141009_1_updated.wav"
        updated_media_data.mime_type = "audio/x-wav"
        updated_media_data.file_length = "1130.3"
        updated_media_data.file_description = "Updated description"
        
        # Import again
        import_media_resources(bundle_resources, [updated_media_data])
        
        # Verify field updates
        assert media_resource.file_name == "ZAG_EOI_20141009_1_updated.wav"
        assert media_resource.file_description == "Updated description"
        assert media_resource.save.called


@pytest.mark.django_db
def test_written_resource_import():
    """Test the written resource import function"""
    # Create a mock bundle resources
    bundle_resources = MagicMock(spec=BundleResources)
    bundle_written_resources = MagicMock()
    bundle_resources.bundle_written_resources = bundle_written_resources
    
    # Create mock written resource data based on real XML
    written_data = MagicMock()
    written_data.file_pid = "hdl:11341/00-0000-0000-0000-1B29-8"
    written_data.file_name = "ZAG_EOI_20141009_1.eaf"
    written_data.mime_type = "text/x-eaf+xml"
    written_data.file_description = None  # XML doesn't have this
    written_data.is_annotation_of = []  # XML doesn't have this
    
    # Patch get_or_create to return a mock
    with patch('lacos.blam.models.bundle.bundle_structural_info.WrittenResource.objects.get_or_create') as mock_get_or_create:
        # Create a mock written resource
        written_resource = MagicMock(spec=WrittenResource)
        written_resource.file_name = written_data.file_name
        written_resource.file_pid = written_data.file_pid
        written_resource.mime_type = written_data.mime_type
        
        # Set up return value
        mock_get_or_create.return_value = (written_resource, True)
        
        # Import written resource
        import_written_resources(bundle_resources, [written_data])
        
        # Verify get_or_create was called with correct parameters
        mock_get_or_create.assert_called_once()
        call_args, call_kwargs = mock_get_or_create.call_args
        assert call_kwargs['file_pid'] == "hdl:11341/00-0000-0000-0000-1B29-8"
        assert call_kwargs['defaults']['file_name'] == "ZAG_EOI_20141009_1.eaf"
        assert call_kwargs['defaults']['mime_type'] == "text/x-eaf+xml"
        
        # Verify add was called with the mock written resource
        bundle_written_resources.add.assert_called_once_with(written_resource)
        
        # Reset mocks for the annotation test
        mock_get_or_create.reset_mock()
        bundle_written_resources.add.reset_mock()
        
        # Create data with annotations
        written_data_with_annotation = MagicMock()
        written_data_with_annotation.file_pid = "test_pid_1"
        written_data_with_annotation.file_name = "transcript.eaf"
        written_data_with_annotation.mime_type = "text/x-eaf+xml"
        written_data_with_annotation.file_description = "Transcription file"
        written_data_with_annotation.is_annotation_of = ["hdl:11341/00-0000-0000-0000-1B28-A"]
        
        # Update return value
        written_resource_with_annotation = MagicMock(spec=WrittenResource)
        written_resource_with_annotation.file_pid = written_data_with_annotation.file_pid
        mock_get_or_create.return_value = (written_resource_with_annotation, True)
        
        # Patch annotation get_or_create
        with patch('lacos.blam.models.bundle.bundle_structural_info.WrittenResourceAnnotation.objects.get_or_create') as mock_annotation_get_or_create:
            # Create a mock annotation
            annotation = MagicMock()
            
            # Set up return value for the annotation
            mock_annotation_get_or_create.return_value = (annotation, True)
            
            # Import written resource with annotation
            import_written_resources(bundle_resources, [written_data_with_annotation])
            
            # Verify annotation creation
            mock_annotation_get_or_create.assert_called_once()
            call_args, call_kwargs = mock_annotation_get_or_create.call_args
            assert call_kwargs['written_resource'] == written_resource_with_annotation
            assert call_kwargs['is_annotation_of'] == "hdl:11341/00-0000-0000-0000-1B28-A"


@pytest.mark.django_db
def test_other_resource_import():
    """Test the other resource import function"""
    # Create a mock bundle resources
    bundle_resources = MagicMock(spec=BundleResources)
    bundle_other_resources = MagicMock()
    bundle_resources.bundle_other_resources = bundle_other_resources
    
    # Create mock other resource data
    other_data = MagicMock()
    other_data.file_pid = "other_pid_1"
    other_data.file_name = "notes.txt"
    other_data.mime_type = "text/plain"
    other_data.file_description = "Field notes"
    
    # Patch get_or_create to return a mock
    with patch('lacos.blam.models.bundle.bundle_structural_info.OtherResource.objects.get_or_create') as mock_get_or_create:
        # Create a mock other resource
        other_resource = MagicMock(spec=OtherResource)
        other_resource.file_name = other_data.file_name
        other_resource.file_pid = other_data.file_pid
        other_resource.mime_type = other_data.mime_type
        other_resource.file_description = other_data.file_description
        
        # Set up return value
        mock_get_or_create.return_value = (other_resource, True)
        
        # Import other resource
        import_other_resources(bundle_resources, [other_data])
        
        # Verify get_or_create was called with correct parameters
        mock_get_or_create.assert_called_once()
        call_args, call_kwargs = mock_get_or_create.call_args
        assert call_kwargs['file_pid'] == "other_pid_1"
        assert call_kwargs['defaults']['file_name'] == "notes.txt"
        assert call_kwargs['defaults']['mime_type'] == "text/plain"
        assert call_kwargs['defaults']['file_description'] == "Field notes"
        
        # Verify add was called with the mock other resource
        bundle_other_resources.add.assert_called_once_with(other_resource)


@pytest.mark.django_db
def test_collection_not_found_error(real_cmd_data):
    """Test that an error is raised when the collection is not found"""
    # We need to look at how the import_structural_info function handles the DoesNotExist exception
    # Let's patch the function to raise the error in a controlled way
    with patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.CollectionGeneralInfo') as mock_model:
        # Set up the objects.get to raise ObjectDoesNotExist
        mock_objects = MagicMock()
        mock_model.objects = mock_objects
        mock_objects.get.side_effect = ObjectDoesNotExist("Collection with id non-existent-id does not exist")
        
        # Test that the function raises ValueError when ObjectDoesNotExist is raised
        with pytest.raises(ValueError) as exc_info:
            import_structural_info(real_cmd_data, "non-existent-id", "DOI")
        
        # Verify the error message
        assert "does not exist" in str(exc_info.value)


@pytest.mark.django_db
def test_additional_metadata_files_import():
    """Test the additional metadata files import function"""
    # Use mock instead of creating database objects
    # Create a mock bundle structural info
    bundle_struct_info = MagicMock(spec=BundleStructuralInfo)
    
    # Set up additional_metadata_files as a mock
    additional_metadata_files = MagicMock()
    bundle_struct_info.additional_metadata_files = additional_metadata_files
    
    # Create mock metadata file data
    metadata_file_data = MagicMock()
    metadata_file_data.file_pid = "metadata_pid_1"
    metadata_file_data.file_name = "metadata.cmdi"
    metadata_file_data.mime_type = "application/xml"
    metadata_file_data.is_metadata_for = "resource_pid_1"
    metadata_file_data.file_description = "CMDI metadata file"
    
    # Patch the get_or_create method for BundleAdditionalMetadataFile
    with patch('lacos.blam.models.bundle.bundle_structural_info.BundleAdditionalMetadataFile.objects.get_or_create') as mock_get_or_create:
        # Create a mock metadata file
        metadata_file = MagicMock(spec=BundleAdditionalMetadataFile)
        metadata_file.file_name = metadata_file_data.file_name
        metadata_file.file_pid = metadata_file_data.file_pid
        metadata_file.mime_type = metadata_file_data.mime_type
        metadata_file.is_metadata_for = metadata_file_data.is_metadata_for
        metadata_file.file_description = metadata_file_data.file_description
        
        # Set up the mock to return our mock file and created=True
        mock_get_or_create.return_value = (metadata_file, True)
        
        # Import metadata file
        import_additional_metadata_files(bundle_struct_info, [metadata_file_data])
        
        # Verify get_or_create was called with correct parameters
        mock_get_or_create.assert_called_once()
        call_args, call_kwargs = mock_get_or_create.call_args
        assert call_kwargs['file_pid'] == "metadata_pid_1"
        assert call_kwargs['defaults']['file_name'] == "metadata.cmdi"
        assert call_kwargs['defaults']['mime_type'] == "application/xml"
        assert call_kwargs['defaults']['is_metadata_for'] == "resource_pid_1"
        assert call_kwargs['defaults']['file_description'] == "CMDI metadata file"
        
        # Verify add was called with the mock file
        additional_metadata_files.add.assert_called_once_with(metadata_file) 