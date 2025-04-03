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


@pytest.fixture
@pytest.mark.django_db
def db_collection():
    """Creates a real Collection and CollectionGeneralInfo in the test database."""
    collection_handle = "hdl:11341/00-0000-0000-0000-1AC6-9" # From real_bundle_xml
    collection_id_type = IdentifierTypeChoices.HANDLE

    # Create necessary related objects if they don't exist or use defaults
    # Assuming CollectionLocation might be needed or handled by defaults/null=True
    location, _ = CollectionLocation.objects.get_or_create(
        # Add necessary defaults or lookup existing
        location_name="Test Location",
        region_name="Test Region",
        country_name="Test Country",
        country_code="XX"
    )

    general_info, created_gi = CollectionGeneralInfo.objects.get_or_create(
        id_value=collection_handle,
        id_type=collection_id_type,
        defaults={
            'display_title': "Zaghawa Test Collection",
            'description': "Test collection for structural info import",
            # Add other required fields for CollectionGeneralInfo if any, or ensure they allow null/blank
            'location': location, # Link the location
        }
    )

    # Create the Collection itself, linking the general info
    collection, created_c = Collection.objects.get_or_create(
        general_info=general_info,
        defaults={
            # Add other required fields for Collection if any
        }
    )
    return collection


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
    # ... (existing setup) ...
    components = real_cmd_data.components
    structural_info_data = components.blam_bundle_repository_v1_0.bundle_structural_info
    collection_id = structural_info_data.bundle_is_member_of_collection.value
    
    # Patch Collection and GeneralInfo lookups
    with patch('lacos.blam.models.collection.collection_general_info.CollectionGeneralInfo.objects.get', return_value=mock_collection.general_info), \
         patch('lacos.blam.models.collection.collection_repository.Collection.objects.get', return_value=mock_collection), \
         patch('lacos.blam.models.bundle.bundle_structural_info.BundleStructuralInfo.objects.get_or_create') as mock_struct_get_or_create, \
         patch('lacos.blam.models.bundle.bundle_structural_info.BundleResources.objects.create') as mock_resources_create, \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_media_resources') as mock_import_media, \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_written_resources') as mock_import_written, \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_other_resources') as mock_import_other, \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_additional_metadata_files') as mock_import_add_meta:

        # --- Mock Setup ---
        # Mock BundleStructuralInfo (initially without resources linked)
        mock_bundle_struct_info = MagicMock(spec=BundleStructuralInfo)
        mock_bundle_struct_info.is_member_of_collection = mock_collection
        mock_bundle_struct_info.resources = None # Start as None
        # We need save to be mockable on this instance
        mock_bundle_struct_info.save = MagicMock()

        # Mock BundleResources (the object that will be created)
        mock_bundle_resources = MagicMock(spec=BundleResources)
        mock_resources_create.return_value = mock_bundle_resources

        # Simulate BundleStructuralInfo get_or_create returning the new mock
        mock_struct_get_or_create.return_value = (mock_bundle_struct_info, True) # Simulate creation

        # --- Call the function under test ---
        result = import_structural_info(real_cmd_data, collection_id, "Handle")

        # --- Assertions ---
        # Verify BundleStructuralInfo was looked up/created correctly
        mock_struct_get_or_create.assert_called_once_with(is_member_of_collection=mock_collection)

        # Verify BundleResources was created because struct_info was new
        mock_resources_create.assert_called_once()

        # Verify the link was saved
        mock_bundle_struct_info.save.assert_called_once_with(update_fields=['resources'])
        # Verify the resource was assigned in memory
        assert mock_bundle_struct_info.resources == mock_bundle_resources

        # Verify the lower-level importers were called with the *created* bundle_resources
        # Check based on the actual XML content loaded by real_cmd_data
        assert structural_info_data.bundle_resources is not None
        if structural_info_data.bundle_resources.media_resource:
            mock_import_media.assert_called_once_with(mock_bundle_resources, structural_info_data.bundle_resources.media_resource)
        else:
            mock_import_media.assert_not_called()

        if structural_info_data.bundle_resources.written_resource:
            mock_import_written.assert_called_once_with(mock_bundle_resources, structural_info_data.bundle_resources.written_resource)
        else:
            mock_import_written.assert_not_called()

        if structural_info_data.bundle_resources.other_resource:
             mock_import_other.assert_called_once_with(mock_bundle_resources, structural_info_data.bundle_resources.other_resource)
        else:
             mock_import_other.assert_not_called()
             
        if structural_info_data.bundle_additional_metadata_file:
             mock_import_add_meta.assert_called_once_with(mock_bundle_struct_info, structural_info_data.bundle_additional_metadata_file)
        else:
             mock_import_add_meta.assert_not_called()


        # Verify the final result is the BundleStructuralInfo instance
        assert result is mock_bundle_struct_info


@pytest.mark.django_db
def test_get_or_create_structural_info_behavior(real_cmd_data, mock_collection):
    # ... (existing setup) ...
    components = real_cmd_data.components
    structural_info_data = components.blam_bundle_repository_v1_0.bundle_structural_info
    collection_id = structural_info_data.bundle_is_member_of_collection.value

    # Patch necessary lookups and creation methods
    with patch('lacos.blam.models.collection.collection_general_info.CollectionGeneralInfo.objects.get', return_value=mock_collection.general_info), \
         patch('lacos.blam.models.collection.collection_repository.Collection.objects.get', return_value=mock_collection), \
         patch('lacos.blam.models.bundle.bundle_structural_info.BundleStructuralInfo.objects.get_or_create') as mock_struct_get_or_create, \
         patch('lacos.blam.models.bundle.bundle_structural_info.BundleResources.objects.create') as mock_resources_create, \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_media_resources'), \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_written_resources'), \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_other_resources'), \
         patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_additional_metadata_files'): # Patch lower-level imports

        # --- Mock Setup ---
        # Mock BundleStructuralInfo for first call (created=True)
        mock_bundle_struct_info_new = MagicMock(spec=BundleStructuralInfo)
        mock_bundle_struct_info_new.is_member_of_collection = mock_collection
        mock_bundle_struct_info_new.resources = None # Start as None
        mock_bundle_struct_info_new.save = MagicMock()

        # Mock BundleResources (the object created on first call)
        mock_bundle_resources = MagicMock(spec=BundleResources)
        mock_resources_create.return_value = mock_bundle_resources

        # Mock BundleStructuralInfo for second call (created=False)
        mock_bundle_struct_info_existing = MagicMock(spec=BundleStructuralInfo)
        mock_bundle_struct_info_existing.is_member_of_collection = mock_collection
        mock_bundle_struct_info_existing.resources = mock_bundle_resources # Already linked
        mock_bundle_struct_info_existing.save = MagicMock() # Still need save method

        # Set up side effect for BundleStructuralInfo.objects.get_or_create
        mock_struct_get_or_create.side_effect = [
            (mock_bundle_struct_info_new, True),      # First call: created
            (mock_bundle_struct_info_existing, False) # Second call: existed
        ]

        # --- Call 1: Create ---
        struct_info1 = import_structural_info(real_cmd_data, collection_id, "Handle")

        # Assertions for call 1
        assert struct_info1 is mock_bundle_struct_info_new
        mock_resources_create.assert_called_once() # Resources should be created
        mock_bundle_struct_info_new.save.assert_called_once_with(update_fields=['resources']) # Link saved
        assert struct_info1.resources == mock_bundle_resources # Link assigned in memory

        # Reset mocks before second call
        mock_resources_create.reset_mock()
        mock_bundle_struct_info_new.save.reset_mock()
        # Note: Don't reset mock_struct_get_or_create as we need its side_effect

        # --- Call 2: Get ---
        struct_info2 = import_structural_info(real_cmd_data, collection_id, "Handle")

        # Assertions for call 2
        assert struct_info2 is mock_bundle_struct_info_existing # Should get existing mock
        mock_resources_create.assert_not_called() # Resources should NOT be created again
        mock_bundle_struct_info_existing.save.assert_not_called() # Save should NOT be called for resources link
        assert struct_info2.resources == mock_bundle_resources # Should have the existing resources linked

        # Final check on get_or_create call count
        assert mock_struct_get_or_create.call_count == 2


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