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
    OtherResource
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

    # 1. Collection Setup
    location, _ = CollectionLocation.objects.get_or_create(
        location_name="Test Location", region_name="Test Region",
        country_name="Test Country", country_code="XX"
    )
    general_info, _ = CollectionGeneralInfo.objects.get_or_create(
        id_value=f"hdl:test/{uuid4()}", id_type=IdentifierTypeChoices.HANDLE,
        defaults={
            'display_title': "Test Collection", 'description': "A test collection",
            'location': location
        }
    )
    admin_info, _ = CollectionAdministrativeInfo.objects.get_or_create(
        access_level='open',
        defaults={'availability_date': date.today()}
    )
    collection_header, _ = CollectionHeader.objects.get_or_create(
        md_self_link=f"hdl:test/collection-header-{uuid4()}",
        defaults={
            'md_creation_date': date.today()
        }
    )
    pub_info, _ = CollectionPublicationInfo.objects.get_or_create(
        publication_year="2024"
    )
    coll_struct_info, _ = CollectionStructuralInfo.objects.get_or_create(
        defaults={}
    )
    objects['collection'] = Collection.objects.create(
        general_info=general_info,
        administrative_info=admin_info,
        base_header=collection_header,
        publication_info=pub_info,
        structural_info=coll_struct_info
    )

    # 2. Bundle Resources Setup
    objects['resources_container'] = BundleResources.objects.create()

    # 3. Structural Info Setup
    objects['struct_info'] = BundleStructuralInfo.objects.create(
        is_member_of_collection=objects['collection'],
        resources=objects['resources_container']
    )

    # 4. Bundle Header Setup
    objects['header'] = BundleHeader.objects.create(
        md_self_link=f"hdl:test/bundle-header-{uuid4()}"
    )

    # 5. Bundle Administrative Info Setup
    bundle_admin_info, _ = BundleAdministrativeInfo.objects.get_or_create(
        access_level='open',
        defaults={'availability_date': date.today()}
    )
    
    # ---> FIX: Create required Bundle Location (if BundleGeneralInfo needs it) <--- 
    # This might be needed by BundleGeneralInfo, adjust if not or if fields differ
    bundle_location, _ = BundleLocation.objects.get_or_create(
        region_name="Test Region",
        country_name="Test Country",
        country_code="XX"
        # Add other required fields for BundleLocation if any
    )
    
    # ---> FIX: Create required Bundle General Info <--- 
    bundle_general_info, _ = BundleGeneralInfo.objects.get_or_create(
        # Assuming display_title is a unique/lookup field or provide a unique one
        display_title=f"Test Bundle {uuid4()}", 
        defaults={
            # Provide necessary defaults for BundleGeneralInfo
            'description': "Test bundle general info",
            'recording_date': date.today(),
            'location': bundle_location # Link the location
            # Add other required fields if any
        }
    )

    # ---> FIX: Create required Bundle Publication Info <--- 
    bundle_pub_info, _ = BundlePublicationInfo.objects.get_or_create(
        # Provide necessary defaults for BundlePublicationInfo
        publication_year="2024" # Reusing same default as collection
        # Add other required fields if any
    )

    # 6. Bundle Setup
    # ---> FIX: Link Bundle Publication Info <--- 
    objects['bundle'] = Bundle.objects.create(
        base_header=objects['header'],
        structural_info=objects['struct_info'],
        administrative_info=bundle_admin_info,
        general_info=bundle_general_info,
        publication_info=bundle_pub_info # Link the created pub info
    )

    # 7. Resource Objects Setup & Link to Container
    objects['media_resource'] = MediaResource.objects.create(
        file_name="test.wav", file_pid=f"hdl:test/{uuid4()}",
        mime_type="audio/wav", file_length="123.45"
    )
    objects['written_resource'] = WrittenResource.objects.create(
        file_name="test.eaf", file_pid=f"hdl:test/{uuid4()}",
        mime_type="text/x-eaf+xml"
    )
    objects['other_resource'] = OtherResource.objects.create(
        file_name="notes.txt", file_pid=f"hdl:test/{uuid4()}",
        mime_type="text/plain"
    )

    # Link resources to the container
    objects['resources_container'].bundle_media_resources.add(objects['media_resource'])
    objects['resources_container'].bundle_written_resources.add(objects['written_resource'])
    objects['resources_container'].bundle_other_resources.add(objects['other_resource'])

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
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/"
    assert resource_mapping_service.construct_s3_path(bundle) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_media_resource(resource_mapping_service, db_objects):
    """Test S3 path construction for a MediaResource object."""
    media_resource = db_objects['media_resource']
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/resources/{media_resource.file_name}"
    assert resource_mapping_service.construct_s3_path(media_resource) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_written_resource(resource_mapping_service, db_objects):
    """Test S3 path construction for a WrittenResource object."""
    written_resource = db_objects['written_resource']
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/resources/{written_resource.file_name}"
    assert resource_mapping_service.construct_s3_path(written_resource) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_for_other_resource(resource_mapping_service, db_objects):
    """Test S3 path construction for an OtherResource object."""
    other_resource = db_objects['other_resource']
    bundle = db_objects['bundle']
    collection = db_objects['collection']
    expected_path = f"collections/{collection.id}/bundles/{bundle.id}/resources/{other_resource.file_name}"
    assert resource_mapping_service.construct_s3_path(other_resource) == expected_path

@pytest.mark.django_db
def test_construct_s3_path_bundle_missing_struct_info(resource_mapping_service, db_objects):
    """Test S3 path construction for a Bundle missing structural_info."""
    bundle = db_objects['bundle']
    bundle.structural_info = None # Simulate missing link
    assert resource_mapping_service.construct_s3_path(bundle) is None

@pytest.mark.django_db
def test_construct_s3_path_bundle_missing_collection_link(resource_mapping_service, db_objects):
    """Test S3 path construction for a Bundle whose structural_info is missing collection link."""
    struct_info = db_objects['struct_info']
    struct_info.is_member_of_collection = None # Simulate missing link
    bundle = db_objects['bundle']
    bundle.structural_info = struct_info 
    assert resource_mapping_service.construct_s3_path(bundle) is None

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
    """Test successful mapping of a complete collection hierarchy."""
    # Setup mocks
    mock_discovery_instance = MagicMock()
    mock_discovery_service.return_value = mock_discovery_instance
    
    # Configure mock responses
    collection_id = db_objects['collection'].id
    bundle_id = db_objects['bundle'].id
    mock_discovery_instance.production_bucket = "test-bucket"
    mock_discovery_instance.form_collection_path.return_value = f"collections/{collection_id}"
    mock_discovery_instance.form_bundle_path.return_value = f"collections/{collection_id}/bundles/{bundle_id}"
    mock_discovery_instance.get_resource_path_pattern.return_value = f"collections/{collection_id}/bundles/{bundle_id}/resources/{{resource_filename}}"
    
    # The actual issue: Resources are accessible via the bundle structural info resources
    # Set up the proper relationship path that the actual implementation expects:
    # Bundle -> structural_info -> resources -> bundle_media_resources, etc.
    
    # Get test objects
    bundle = db_objects['bundle']
    struct_info = db_objects['struct_info']
    resources_container = db_objects['resources_container']
    
    # This is the correct layout for resource access in the real code
    # resources_container already has the resources linked in the db_objects fixture
    # We just need to make sure all relationships are properly connected
    
    # Confirm the bundle is properly linked to these resources
    assert bundle.structural_info == struct_info
    assert struct_info.resources == resources_container
    
    # Confirm the resources are properly linked
    assert resources_container.bundle_media_resources.filter(id=db_objects['media_resource'].id).exists()
    assert resources_container.bundle_written_resources.filter(id=db_objects['written_resource'].id).exists()
    assert resources_container.bundle_other_resources.filter(id=db_objects['other_resource'].id).exists()
    
    # Call the method
    result = resource_mapping_service.map_collection_hierarchy(collection_id)
    
    # Verify the result
    # We should have 5 S3ResourceLocations: 1 collection, 1 bundle, 3 resources
    assert result == 5
    
    # Check that ResourceMappingService created the correct number of S3ResourceLocation objects
    s3_locations = S3ResourceLocation.objects.all()
    assert s3_locations.count() == 5
    
    # Verify collection mapping
    collection_ct = ContentType.objects.get_for_model(Collection)
    collection_location = S3ResourceLocation.objects.get(
        content_type=collection_ct,
        object_id=collection_id
    )
    assert collection_location.s3_bucket == "test-bucket"
    assert collection_location.s3_key == f"collections/{collection_id}/"
    
    # Verify bundle mapping
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    bundle_location = S3ResourceLocation.objects.get(
        content_type=bundle_ct,
        object_id=bundle_id
    )
    assert bundle_location.s3_bucket == "test-bucket"
    assert bundle_location.s3_key == f"collections/{collection_id}/bundles/{bundle_id}/"
    
    # Verify resource mappings (one of each type)
    media_resource = db_objects['media_resource']
    media_ct = ContentType.objects.get_for_model(MediaResource)
    media_location = S3ResourceLocation.objects.get(
        content_type=media_ct,
        object_id=media_resource.id
    )
    assert media_location.s3_bucket == "test-bucket"
    assert media_location.s3_key == f"collections/{collection_id}/bundles/{bundle_id}/resources/{media_resource.file_name}"
    
    # Verify method calls
    mock_discovery_instance.form_collection_path.assert_called_once_with(collection_id)
    mock_discovery_instance.form_bundle_path.assert_called_once_with(collection_id, bundle_id)
    mock_discovery_instance.get_resource_path_pattern.assert_called_once()

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

# --- Add more tests for other methods like register_s3_location if needed ---
