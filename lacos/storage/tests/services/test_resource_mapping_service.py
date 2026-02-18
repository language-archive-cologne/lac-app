import pytest
from uuid import uuid4
from datetime import date
from unittest.mock import patch, MagicMock

# Models needed for testing
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleResources,
    MediaResource,
    WrittenResource,
    OtherResource,
    BundleAdditionalMetadataFile,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from django.contrib.contenttypes.models import ContentType

# Service to test
from lacos.storage.services.resource_mapping_service import ResourceMappingService


@pytest.fixture
def resource_mapping_service():
    """Provides an instance of the ResourceMappingService."""
    # Assuming default initialization is okay for tests
    return ResourceMappingService()

@pytest.fixture
@pytest.mark.django_db
def db_objects():
    """
    Creates a chain of related objects in the test database:
    Collection -> Bundle -> StructuralInfo -> Resources -> Media/Written/OtherResource
    """
    objects = {}

    # 1. First create the Collection object since related objects now have FKs to it
    objects['collection'] = Collection.objects.create(
        identifier=f"test-collection-{uuid4()}"
    )

    # 2. Create Collection-related objects
    location = CollectionLocation.objects.create(
        location_name="Test Location", region_name="Test Region",
        country_name="Test Country", country_code="XX"
    )
    
    collection_header = CollectionHeader.objects.create(
        collection=objects['collection'],
        md_self_link=f"hdl:test/collection-header-{uuid4()}",
        md_creation_date=date.today()
    )
    
    general_info = CollectionGeneralInfo.objects.create(
        collection=objects['collection'],
        id_value=f"hdl:test/{uuid4()}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Test Collection",
        description="A test collection",
        location=location
    )
    
    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=objects['collection'],
        access_level='open',
        availability_date=date.today()
    )
    
    pub_info = CollectionPublicationInfo.objects.create(
        collection=objects['collection'],
        publication_year="2024"
    )
    
    coll_struct_info = CollectionStructuralInfo.objects.create(
        collection=objects['collection']
    )

    # 3. Create the Bundle object
    objects['bundle'] = Bundle.objects.create(
        identifier=f"test-bundle-{uuid4()}"
    )
    
    # 4. Create Bundle-related objects
    objects['header'] = BundleHeader.objects.create(
        bundle=objects['bundle'],
        md_self_link=f"hdl:test/bundle-header-{uuid4()}"
    )
    
    bundle_admin_info = BundleAdministrativeInfo.objects.create(
        bundle=objects['bundle'],
        access_level='open',
        availability_date=date.today()
    )
    
    bundle_location = BundleLocation.objects.create(
        region_name="Test Region",
        country_name="Test Country",
        country_code="XX"
    )
    
    bundle_general_info = BundleGeneralInfo.objects.create(
        bundle=objects['bundle'],
        display_title=f"Test Bundle {uuid4()}",
        description="Test bundle general info",
        recording_date=date.today(),
        location=bundle_location
    )
    
    bundle_pub_info = BundlePublicationInfo.objects.create(
        bundle=objects['bundle'],
        publication_year="2024"
    )

    # 5. Create resources container and structural info
    objects['resources_container'] = BundleResources.objects.create(
        bundle=objects['bundle']
    )
    
    # Create structural info that links bundle to collection
    objects['struct_info'] = BundleStructuralInfo.objects.create(
        bundle=objects['bundle'],
        is_member_of_collection=objects['collection']
    )
    
    # 6. Create and link resources
    media_resource = MediaResource.objects.create(
        file_name="test.wav",
        mime_type="audio/wav",
        file_pid=f"hdl:test/{uuid4()}",
        file_length="123.45"
    )
    objects['media_resource'] = media_resource
    objects['resources_container'].bundle_media_resources.add(media_resource)
    
    written_resource = WrittenResource.objects.create(
        file_name="test.eaf",
        mime_type="text/xml",
        file_pid=f"hdl:test/{uuid4()}"
    )
    objects['written_resource'] = written_resource
    objects['resources_container'].bundle_written_resources.add(written_resource)
    
    other_resource = OtherResource.objects.create(
        file_name="notes.txt",
        mime_type="text/plain",
        file_pid=f"hdl:test/{uuid4()}"
    )
    objects['other_resource'] = other_resource
    objects['resources_container'].bundle_other_resources.add(other_resource)

    return objects


# --- Tests for construct_s3_path ---

@pytest.mark.django_db
def test_construct_s3_path_for_collection(resource_mapping_service, db_objects):
    """Test S3 path construction for a Collection object."""
    collection = db_objects['collection']
    expected_path = f"collections/{collection.id}/"
    assert resource_mapping_service.construct_s3_path(collection) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_bundle(resource_mapping_service, db_objects):
    """Test S3 path construction for a Bundle object."""
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    
    # Verify the relationship exists
    assert bundle.structural_info.filter(is_member_of_collection=collection).exists()
    
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/"
    assert resource_mapping_service.construct_s3_path(bundle) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_media_resource(resource_mapping_service, db_objects):
    """Test S3 path construction for a MediaResource object."""
    media_resource = db_objects['media_resource']
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    
    # Verify resource is correctly connected to bundle
    bundle_resources = BundleResources.objects.filter(bundle=bundle).first()
    assert bundle_resources.bundle_media_resources.filter(id=media_resource.id).exists()
    
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/resources/{media_resource.file_name}"
    assert resource_mapping_service.construct_s3_path(media_resource) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_written_resource(resource_mapping_service, db_objects):
    """Test S3 path construction for a WrittenResource object."""
    written_resource = db_objects['written_resource']
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    
    # Verify resource is correctly connected to bundle
    bundle_resources = BundleResources.objects.filter(bundle=bundle).first()
    assert bundle_resources.bundle_written_resources.filter(id=written_resource.id).exists()
    
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/resources/{written_resource.file_name}"
    assert resource_mapping_service.construct_s3_path(written_resource) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_other_resource(resource_mapping_service, db_objects):
    """Test S3 path construction for an OtherResource object."""
    other_resource = db_objects['other_resource']
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    
    # Verify resource is correctly connected to bundle
    bundle_resources = BundleResources.objects.filter(bundle=bundle).first()
    assert bundle_resources.bundle_other_resources.filter(id=other_resource.id).exists()
    
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/resources/{other_resource.file_name}"
    assert resource_mapping_service.construct_s3_path(other_resource) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_bundle_missing_struct_info(resource_mapping_service, db_objects):
    """Test S3 path construction for a Bundle missing structural_info."""
    # Create a new bundle without a structural_info
    standalone_bundle = Bundle.objects.create(identifier=f"test-standalone-{uuid4()}")
    assert resource_mapping_service.construct_s3_path(standalone_bundle) is None

@pytest.mark.django_db
def test_construct_s3_path_bundle_missing_collection_link(resource_mapping_service, db_objects):
    """Test S3 path construction for a Bundle whose structural_info is missing collection link."""
    # Instead of creating a bundle without a collection link (which now fails due to NOT NULL constraint),
    # we'll create a bundle that has no structural_info at all, as this is equivalent for testing purposes
    standalone_bundle = Bundle.objects.create(identifier=f"test-no-collection-{uuid4()}")
    # Don't create any structural info, which means it can't find a collection
    assert resource_mapping_service.construct_s3_path(standalone_bundle) is None

@pytest.mark.django_db
def test_construct_s3_path_resource_missing_filename(resource_mapping_service, db_objects):
    """Test S3 path construction for a Resource missing its file_name."""
    media_resource = db_objects['media_resource']
    media_resource.file_name = "" # Simulate missing file name
    assert resource_mapping_service.construct_s3_path(media_resource) is None

    media_resource.file_name = None # Simulate missing file name
    assert resource_mapping_service.construct_s3_path(media_resource) is None

@pytest.mark.django_db
def test_construct_s3_path_unrecognized_object(resource_mapping_service):
    """Test S3 path construction for an object type not handled."""
    class UnrecognizedObject:
        id = 123
    
    unrecognized = UnrecognizedObject()
    assert resource_mapping_service.construct_s3_path(unrecognized) is None

# --- Tests for map_collection_hierarchy method ---

@pytest.mark.django_db
@patch('lacos.storage.services.file_discovery_service.FileDiscoveryService')
def test_map_collection_hierarchy_successful(mock_discovery_service, resource_mapping_service, db_objects):
    """Test successful mapping of a complete collection hierarchy, including resources."""
    # Setup mocks
    mock_discovery_instance = MagicMock()
    mock_discovery_service.return_value = mock_discovery_instance
    
    # Configure mock responses
    collection = db_objects['collection']
    bundle = db_objects['bundle']
    media_resource = db_objects['media_resource']
    written_resource = db_objects['written_resource']
    other_resource = db_objects['other_resource']
    collection_id = collection.id
    bundle_id = bundle.id
    
    mock_discovery_instance.production_bucket = "test-bucket"
    mock_discovery_instance.form_collection_path.return_value = f"collections/{collection_id}"
    mock_discovery_instance.form_bundle_path.return_value = f"collections/{collection_id}/bundles/{bundle_id}"
    # Define the base resource path using the pattern
    resource_path_pattern = "collections/{collection_id}/bundles/{bundle_id}/resources/{resource_filename}"
    mock_discovery_instance.get_resource_path_pattern.return_value = resource_path_pattern
    resources_base_key = f"collections/{collection_id}/bundles/{bundle_id}/resources/"
    
    # Verify the relationships are set correctly in the fixture
    assert bundle.structural_info.filter(is_member_of_collection=collection).exists()
    # Explicitly fetch the BundleResources instance
    bundle_resources = BundleResources.objects.filter(bundle=bundle).first()
    if bundle_resources:
        assert bundle_resources.bundle_media_resources.filter(id=media_resource.id).exists()
        assert bundle_resources.bundle_written_resources.filter(id=written_resource.id).exists()
        assert bundle_resources.bundle_other_resources.filter(id=other_resource.id).exists()
    else:
        pytest.fail(f"Could not find BundleResources instance for Bundle {bundle.id} via direct query...")
        
    # Test mapping
    mapped_count = resource_mapping_service.map_collection_hierarchy(collection.id)
    
    # Should map 1 Collection + 1 Bundle + 3 Resources = 5
    assert mapped_count == 5
    
    # Verify mocks were called correctly (adjust if needed based on discovery service usage)
    mock_discovery_instance.form_collection_path.assert_called_with(collection.id)
    mock_discovery_instance.form_bundle_path.assert_called_with(collection.id, bundle.id)
    mock_discovery_instance.get_resource_path_pattern.assert_called()
    
    # Verify S3ResourceLocation objects were created for all items
    # Collection
    collection_ct = ContentType.objects.get_for_model(Collection)
    col_loc = S3ResourceLocation.objects.get(content_type=collection_ct, object_id=collection.id)
    assert col_loc.s3_key == f"collections/{collection_id}/"
    
    # Bundle
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    bun_loc = S3ResourceLocation.objects.get(content_type=bundle_ct, object_id=bundle.id)
    assert bun_loc.s3_key == f"collections/{collection_id}/bundles/{bundle_id}/"
    
    # Media Resource
    media_ct = ContentType.objects.get_for_model(MediaResource)
    media_loc = S3ResourceLocation.objects.get(content_type=media_ct, object_id=media_resource.id)
    assert media_loc.s3_key == f"{resources_base_key}{media_resource.file_name}"
    assert media_loc.resource_pid == media_resource.file_pid # Check PID was registered
    
    # Written Resource
    written_ct = ContentType.objects.get_for_model(WrittenResource)
    written_loc = S3ResourceLocation.objects.get(content_type=written_ct, object_id=written_resource.id)
    assert written_loc.s3_key == f"{resources_base_key}{written_resource.file_name}"
    assert written_loc.resource_pid == written_resource.file_pid
    
    # Other Resource
    other_ct = ContentType.objects.get_for_model(OtherResource)
    other_loc = S3ResourceLocation.objects.get(content_type=other_ct, object_id=other_resource.id)
    assert other_loc.s3_key == f"{resources_base_key}{other_resource.file_name}"
    assert other_loc.resource_pid == other_resource.file_pid

@pytest.mark.django_db
@patch('lacos.storage.services.file_discovery_service.FileDiscoveryService')
def test_map_collection_hierarchy_collection_not_found(mock_discovery_service, resource_mapping_service):
    """Test mapping with a non-existent collection ID."""
    # Setup
    non_existent_id = uuid4()
    mock_discovery_instance = MagicMock()
    mock_discovery_service.return_value = mock_discovery_instance
    
    # Call the method
    result = resource_mapping_service.map_collection_hierarchy(non_existent_id)
    
    # Verify result
    assert result == 0
    assert S3ResourceLocation.objects.count() == 0

@pytest.mark.django_db
@patch('lacos.storage.services.file_discovery_service.FileDiscoveryService')
def test_map_collection_hierarchy_exception_in_collection_mapping(mock_discovery_service, resource_mapping_service, db_objects):
    """Test handling of exceptions during collection mapping."""
    # Setup
    collection_id = db_objects['collection'].id
    mock_discovery_instance = MagicMock()
    mock_discovery_service.return_value = mock_discovery_instance
    
    # Configure mock to raise exception during collection mapping
    mock_discovery_instance.production_bucket = "test-bucket"
    mock_discovery_instance.form_collection_path.side_effect = ValueError("Test error")
    
    # Call the method
    result = resource_mapping_service.map_collection_hierarchy(collection_id)
    
    # The method should continue to map bundles and resources even if collection mapping fails
    # Since form_collection_path fails, we can't check exact count, but should be less than 5
    assert result < 5
    
    # Verify method calls
    mock_discovery_instance.form_collection_path.assert_called_once_with(collection_id)

@pytest.mark.django_db
@patch('lacos.storage.services.file_discovery_service.FileDiscoveryService')
def test_map_collection_hierarchy_exception_in_bundle_mapping(mock_discovery_service, resource_mapping_service, db_objects):
    """Test handling of exceptions during bundle mapping."""
    # Setup
    collection_id = db_objects['collection'].id
    bundle_id = db_objects['bundle'].id
    mock_discovery_instance = MagicMock()
    mock_discovery_service.return_value = mock_discovery_instance
    
    # Configure mocks
    mock_discovery_instance.production_bucket = "test-bucket"
    mock_discovery_instance.form_collection_path.return_value = f"collections/{collection_id}"
    # Make form_bundle_path raise an exception
    mock_discovery_instance.form_bundle_path.side_effect = ValueError("Test error")
    
    # Call the method
    result = resource_mapping_service.map_collection_hierarchy(collection_id)
    
    # We should have at least the collection mapped (1)
    assert result >= 1
    
    # Verify at least the collection was mapped
    collection_ct = ContentType.objects.get_for_model(Collection)
    collection_location = S3ResourceLocation.objects.get(
        content_type=collection_ct,
        object_id=collection_id
    )
    assert collection_location.s3_bucket == "test-bucket"
    assert collection_location.s3_key == f"collections/{collection_id}/"
    
    # Verify method calls
    mock_discovery_instance.form_collection_path.assert_called_once_with(collection_id)
    mock_discovery_instance.form_bundle_path.assert_called_once_with(collection_id, bundle_id)


@pytest.mark.django_db
@patch('lacos.storage.services.file_discovery_service.FileDiscoveryService')
def test_map_collection_hierarchy_maps_bundle_additional_metadata(
    mock_discovery_service,
    resource_mapping_service,
    db_objects,
):
    """Bundle additional metadata files should be registered in S3ResourceLocation."""
    collection = db_objects['collection']
    bundle = db_objects['bundle']
    collection_id = collection.id
    bundle_id = bundle.id

    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_name="bundle-metadata.xml",
        mime_type="application/xml",
        file_pid=f"hdl:test/{uuid4()}",
        is_metadata_for="hdl:test/resource",
    )
    db_objects['struct_info'].additional_metadata_files.add(metadata_file)

    mock_discovery_instance = MagicMock()
    mock_discovery_service.return_value = mock_discovery_instance

    mock_discovery_instance.production_bucket = "test-bucket"
    mock_discovery_instance.form_collection_path.return_value = f"collections/{collection_id}"
    mock_discovery_instance.form_bundle_path.return_value = f"collections/{collection_id}/bundles/{bundle_id}"
    mock_discovery_instance.get_resource_path_pattern.return_value = (
        "collections/{collection_id}/bundles/{bundle_id}/resources/{resource_filename}"
    )

    mapped_count = resource_mapping_service.map_collection_hierarchy(collection.id)

    # 1 Collection + 1 Bundle + 3 regular resources + 1 bundle metadata file
    assert mapped_count == 6

    metadata_ct = ContentType.objects.get_for_model(BundleAdditionalMetadataFile)
    metadata_loc = S3ResourceLocation.objects.get(
        content_type=metadata_ct,
        object_id=metadata_file.id,
    )
    assert metadata_loc.s3_bucket == "test-bucket"
    assert metadata_loc.s3_key == (
        f"collections/{collection_id}/bundles/{bundle_id}/resources/{metadata_file.file_name}"
    )

# --- Add more tests for other methods like register_s3_location if needed ---

@pytest.mark.django_db
def test_create_resource_location_for_multiple_object_types(mock_s3):
    """Test creating resource locations for Collection, Bundle and Media objects"""
    # Create test objects with the new model relationship structure
    objects = {}
    # Create Collection with required identifier
    objects['collection'] = Collection.objects.create(
        identifier="test-mapping-collection"
    )
    # Create Bundle with required identifier
    objects['bundle'] = Bundle.objects.create(
        identifier="test-mapping-bundle"
    )
    
    # Create structural info that links bundle to collection
    objects['struct_info'] = BundleStructuralInfo.objects.create(
        bundle=objects['bundle'],
        is_member_of_collection=objects['collection']
    )
    
    # Create BundleResources container
    objects['resources_container'] = BundleResources.objects.create(
        bundle=objects['bundle']
    )
    
    # Create media resource and link it to the bundle
    media_resource = MediaResource.objects.create(
        file_name="test-mapping.wav",
        mime_type="audio/wav",
        file_pid="hdl:test/mapping-resource"
    )
    objects['resources_container'].bundle_media_resources.add(media_resource)
    
    # Create the service and register objects
    service = ResourceMappingService(skip_bucket_check=True)
    
    # Register collection
    collection_location = service.register_s3_location(
        objects['collection'], 
        bucket="test-bucket",
        key=f"collections/{objects['collection'].id}/"
    )
    assert collection_location.s3_bucket == "test-bucket"
    assert collection_location.s3_key == f"collections/{objects['collection'].id}/"
    
    # Register bundle
    bundle_location = service.register_s3_location(
        objects['bundle'], 
        bucket="test-bucket",
        key=f"collections/{objects['collection'].id}/bundles/{objects['bundle'].id}/"
    )
    assert bundle_location.s3_bucket == "test-bucket"
    assert bundle_location.s3_key == f"collections/{objects['collection'].id}/bundles/{objects['bundle'].id}/"
    
    # Register media resource
    resource_location = service.register_s3_location(
        media_resource, 
        bucket="test-bucket",
        key=f"collections/{objects['collection'].id}/bundles/{objects['bundle'].id}/resources/{media_resource.file_name}"
    )
    assert resource_location.s3_bucket == "test-bucket"
    assert resource_location.s3_key == f"collections/{objects['collection'].id}/bundles/{objects['bundle'].id}/resources/{media_resource.file_name}"
    
    # Test that we can retrieve the locations
    assert service.get_s3_location(objects['collection']) == collection_location
    assert service.get_s3_location(objects['bundle']) == bundle_location
    assert service.get_s3_location(media_resource) == resource_location


@pytest.mark.django_db
def test_resolve_pid_to_s3_accepts_hdl_and_handle_url_forms():
    """PID resolution should work for both hdl: and hdl.handle.net forms."""
    collection = Collection.objects.create(identifier="pid-form-collection")
    bundle = Bundle.objects.create(identifier="pid-form-bundle")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    resources = BundleResources.objects.create(bundle=bundle)
    media_resource = MediaResource.objects.create(
        file_name="pid-form.wav",
        mime_type="audio/wav",
        file_pid="hdl:11341/0000-0000-0000-3D03",
    )
    resources.bundle_media_resources.add(media_resource)

    content_type = ContentType.objects.get_for_model(media_resource)
    location = S3ResourceLocation.objects.create(
        content_type=content_type,
        object_id=media_resource.id,
        resource_pid="https://hdl.handle.net/11341/0000-0000-0000-3D03",
        s3_bucket="test-bucket",
        s3_key="any/path/Wooinap_family_situation.imdi",
    )

    service = ResourceMappingService(skip_bucket_check=True)
    resolved = service.resolve_pid_to_s3("hdl:11341/0000-0000-0000-3D03")

    assert resolved is not None
    assert resolved.id == location.id
