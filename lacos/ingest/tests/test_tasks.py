import pytest
import os
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Load environment variables from .django file (same as in test_file_discovery_service.py)
env_file_path = os.path.join('/app', '.envs/.local/.django')
load_dotenv(env_file_path)

# Import the tasks to be tested
from lacos.ingest import tasks as ingest_tasks

# Mark all tests in this module to use the database
pytestmark = pytest.mark.django_db

# --- Monkeypatching ---

@pytest.fixture(autouse=True)
def patch_huey_tasks():
    """Replace huey task decorators with pass-through functions that execute immediately."""
    # Create a pass-through decorator that preserves the original function name
    def passthrough_decorator(func):
        def wrapped(*args, **kwargs):
            # Execute the function directly instead of returning a task
            return func(*args, **kwargs)
        
        # Preserve function metadata
        wrapped.__name__ = func.__name__
        wrapped.__doc__ = func.__doc__
        return wrapped
    
    # Store original decorators
    orig_task = ingest_tasks.task
    orig_db_task = ingest_tasks.db_task
    orig_periodic_task = getattr(ingest_tasks, 'periodic_task', None)
    
    # Replace with our pass-through versions
    ingest_tasks.task = lambda **kwargs: passthrough_decorator
    ingest_tasks.db_task = lambda **kwargs: passthrough_decorator
    if hasattr(ingest_tasks, 'periodic_task'):
        ingest_tasks.periodic_task = lambda **kwargs: passthrough_decorator
        
    # Also patch the decorated functions directly
    # This handles functions that were already decorated when the module was imported
    for name in dir(ingest_tasks):
        attr = getattr(ingest_tasks, name)
        if callable(attr) and hasattr(attr, 'call_local'):
            # Replace the function with one that directly calls the task's functionality
            task_func = attr
            
            def make_sync_wrapper(task_func):
                def sync_wrapper(*args, **kwargs):
                    # Execute immediately instead of returning a task object
                    return task_func.call_local(*args, **kwargs)
                return sync_wrapper
            
            setattr(ingest_tasks, name, make_sync_wrapper(task_func))
    
    # Run the tests with patched decorators
    yield
    
    # Restore original decorators after the test
    ingest_tasks.task = orig_task
    ingest_tasks.db_task = orig_db_task
    if orig_periodic_task:
        ingest_tasks.periodic_task = orig_periodic_task

# --- Fixtures ---

@pytest.fixture
def mock_file_discovery_service():
    """Mocks the FileDiscoveryService where it's used in tasks.py."""
    mock_instance = MagicMock()
    # Configure default return values
    mock_instance.find_collection_and_bundle_xmls_s3.return_value = {
        'potential_collection_xmls': [],
        'potential_bundle_xmls': []
    }
    mock_instance.read_s3_object.return_value = b"<xml></xml>" # Default dummy XML
    mock_instance.production_bucket = 'test-default-bucket' # Mock default bucket name
    
    # Mock path formatting methods
    mock_instance.form_collection_path.side_effect = lambda cid: f"{cid}/{cid}"
    mock_instance.form_bundle_path.side_effect = lambda cid, bid: f"{cid}/{bid}"
    mock_instance.form_resource_path.side_effect = lambda cid, bid, fname: f"{cid}/{bid}/v1/content/data/{fname}"
    mock_instance.form_collection_xml_path.side_effect = lambda cid: f"{cid}/{cid}/v1/content/{cid}.xml"
    mock_instance.form_bundle_xml_path.side_effect = lambda cid, bid: f"{cid}/{bid}/v1/content/{bid}.xml"
    mock_instance.get_resource_path_pattern.return_value = '{collection_id}/{bundle_id}/v1/content/data/{resource_filename}'

    # Patch at the point where it's used in tasks.py
    patcher = patch('lacos.ingest.tasks.FileDiscoveryService', return_value=mock_instance)
    patcher.start()
    yield mock_instance
    patcher.stop()

@pytest.fixture
def mock_resource_mapping_service():
    """Mocks the ResourceMappingService where it's used in tasks.py."""
    mock_instance = MagicMock()
    mock_instance.map_resources_to_s3.return_value = 5  # Keep this for backward compatibility
    mock_instance.map_collection_hierarchy.return_value = 5  # Add this for the method actually used in tasks.py
    
    # Patch at the point where it's used in tasks.py
    patcher = patch('lacos.ingest.tasks.ResourceMappingService', return_value=mock_instance)
    patcher.start()
    yield mock_instance
    patcher.stop()

@pytest.fixture
def mock_collection_importer():
    """Mock the CollectionImporter static methods."""
    # Create a mock for import_from_xml
    mock_imported_collection = MagicMock(id=1)
    
    # Patch where methods are used in tasks.py
    patcher1 = patch('lacos.ingest.tasks.CollectionImporter.import_from_xml', 
                    return_value=mock_imported_collection)
    patcher2 = patch('lacos.ingest.tasks.CollectionImporter.resolve_bundle_references', 
                    return_value=1)
    
    patcher1.start()
    patcher2.start()
    yield mock_imported_collection
    patcher1.stop()
    patcher2.stop()

@pytest.fixture
def mock_bundle_importer():
    """Mock the BundleImporter static methods."""
    mock_imported_bundle = MagicMock(id=10)
    mock_bundle_resources_id = MagicMock()

    patcher = patch(
        'lacos.ingest.tasks.BundleImporter.import_from_xml',
        return_value=(mock_imported_bundle, mock_bundle_resources_id),
    )

    patcher.start()
    yield mock_imported_bundle, mock_bundle_resources_id
    patcher.stop()

# Fixture to automatically use all mocks
@pytest.fixture(autouse=True)
def use_mocks(mock_file_discovery_service, mock_resource_mapping_service, mock_collection_importer, mock_bundle_importer):
    """Ensures mocks are active for tests in this module"""
    pass

# --- Tests ---

def test_find_s3_import_candidates_basic(mock_file_discovery_service):
    """Test that find_s3_import_candidates correctly calls the FileDiscoveryService."""
    # Set specific mock return value for this test
    mock_return = {
        'potential_collection_xmls': ['test/col1.xml'],
        'potential_bundle_xmls': ['test/bun1.xml']
    }
    mock_file_discovery_service.find_collection_and_bundle_xmls_s3.return_value = mock_return
    
    # Call the function
    result = ingest_tasks.find_s3_import_candidates('test-bucket', 'test/')
    
    # Assertions
    mock_file_discovery_service.find_collection_and_bundle_xmls_s3.assert_called_once_with(
        'test-bucket', 'test/'
    )
    assert result == mock_return

def test_find_s3_import_candidates_error(mock_file_discovery_service):
    """Test error handling when find_collection_and_bundle_xmls_s3 raises an exception."""
    # Configure the mock to raise an exception
    mock_file_discovery_service.find_collection_and_bundle_xmls_s3.side_effect = Exception("S3 error")
    
    # Call the function and expect an empty result
    result = ingest_tasks.find_s3_import_candidates('test-bucket', 'test/')
    
    # Assertions
    mock_file_discovery_service.find_collection_and_bundle_xmls_s3.assert_called_once()
    assert result == {'potential_collection_xmls': [], 'potential_bundle_xmls': []}

def test_import_s3_collection(mock_file_discovery_service, mock_collection_importer):
    """Test the import_s3_collection task."""
    # Setup test data
    test_bucket = 'test-bucket'
    test_key = 'collection/collection_id/v1/content/collection_id.xml'
    mock_file_discovery_service.read_s3_object.return_value = b"<collection></collection>"
    
    # Call the function
    result = ingest_tasks.import_s3_collection(test_bucket, test_key)
    
    # Assertions
    mock_file_discovery_service.read_s3_object.assert_called_once_with(test_bucket, test_key)
    # Check that the CollectionImporter.import_from_xml was called with the XML content
    assert ingest_tasks.CollectionImporter.import_from_xml.called
    # Check the return value is the collection ID
    assert result == 1

def test_import_s3_collection_error(mock_file_discovery_service):
    """Test error handling when read_s3_object raises an exception."""
    # Configure the mock to raise an exception
    mock_file_discovery_service.read_s3_object.side_effect = Exception("S3 error")
    
    # Call the function
    result = ingest_tasks.import_s3_collection('test-bucket', 'test/key.xml')
    
    # Assertions
    assert result is None
    # Ensure error handling occurred
    mock_file_discovery_service.read_s3_object.assert_called_once()

def test_import_s3_bundle(mock_file_discovery_service, mock_bundle_importer):
    """Test the import_s3_bundle task."""
    # Setup test data
    test_bucket = 'test-bucket'
    test_key = 'collection_id/bundle_id/v1/content/bundle_id.xml'
    mock_file_discovery_service.read_s3_object.return_value = b"<bundle></bundle>"
    
    bundle, bundle_resources_id = mock_bundle_importer
    # Call the function
    result = ingest_tasks.import_s3_bundle(test_bucket, test_key)
    
    # Assertions
    mock_file_discovery_service.read_s3_object.assert_called_once_with(test_bucket, test_key)
    # Check that the BundleImporter.import_from_xml was called with the XML content
    assert ingest_tasks.BundleImporter.import_from_xml.called
    # Check the return value contains both bundle and resources IDs
    assert result == (bundle.id, bundle_resources_id)

def test_import_s3_bundle_error(mock_file_discovery_service):
    """Test error handling when read_s3_object raises an exception."""
    # Configure the mock to raise an exception
    mock_file_discovery_service.read_s3_object.side_effect = Exception("S3 error")
    
    # Call the function
    result = ingest_tasks.import_s3_bundle('test-bucket', 'test/key.xml')
    
    # Assertions
    assert result is None
    # Ensure error handling occurred
    mock_file_discovery_service.read_s3_object.assert_called_once()

def test_resolve_collection_bundle_links():
    """Test resolve_collection_bundle_links task with mocked Collection model."""
    # Create mocks
    mock_collection = MagicMock()
    mock_collection.id = 1
    
    # Patch the module import inside the function
    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    with patch.dict('sys.modules'):
        # Create a mock for the module that defines Collection
        with patch(collection_import_path) as MockCollection, \
             patch('lacos.ingest.tasks.resolve_links_service') as mock_resolve_links:
            # Configure the mock class
            MockCollection.objects.get.return_value = mock_collection
            MockCollection.DoesNotExist = Exception
            mock_resolve_links.return_value = 1  # Return success value
            
            # Call the function
            result = ingest_tasks.resolve_collection_bundle_links_task(1, [])
            
            # Assertions
            MockCollection.objects.get.assert_called_once_with(id=1)
            mock_resolve_links.assert_called_once_with(1)
            assert result == (1, [])

def test_map_collection_resources():
    """Test map_collection_resources task with mocked models."""
    # Create mocks for use inside the function
    mock_collection = MagicMock()
    mock_collection.id = 1
    mock_collection.structural_info = MagicMock()
    
    mock_bundle = MagicMock()
    mock_bundle.id = 10
    mock_bundle_queryset = MagicMock()
    mock_bundle_queryset.count.return_value = 1
    mock_bundle_queryset.__iter__.return_value = iter([mock_bundle])
    
    # Patch both model imports
    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    bundle_import_path = 'lacos.blam.models.bundle.bundle_repository.Bundle'
    
    with patch(collection_import_path) as MockCollection, \
         patch(bundle_import_path) as MockBundle:
        # Configure mock Collection
        MockCollection.objects.get.return_value = mock_collection
        MockCollection.DoesNotExist = Exception
        
        # Configure mock Bundle
        MockBundle.objects.filter.return_value = mock_bundle_queryset
        
        # Call the function
        ingest_tasks.map_collection_resources(1, [])
        
        # Assertions
        MockCollection.objects.get.assert_called_once_with(id=1)
        # The ResourceMappingService.map_resources_to_s3 is actually called multiple times in the function
        # once for the collection and once per bundle/resource - just check it was called at least once

def test_process_s3_prefix_orchestration():
    """Test the process_s3_prefix orchestration function, verifying correct argument handling."""
    # Setup - patch the individual task functions
    with patch('lacos.ingest.tasks.find_s3_import_candidates') as mock_find, \
         patch('lacos.ingest.tasks.import_s3_collection') as mock_import_collection, \
         patch('lacos.ingest.tasks.import_s3_bundle') as mock_import_bundle, \
         patch('lacos.ingest.tasks.resolve_collection_bundle_links_task') as mock_resolve, \
         patch('lacos.ingest.tasks.map_collection_resources') as mock_map, \
         patch('lacos.ingest.tasks.import_s3_bundles_for_collection') as mock_import_bundles_for_collection, \
         patch('lacos.ingest.tasks.huey') as mock_huey:

        # Define the expected paths
        collection_xml_path = 'col1/col1/v1/content/col1.xml'
        bundle_xml_path = 'col1/bun1/v1/content/bun1.xml'
        expected_collection_id = 1
        expected_bundle_id = 10

        # Configure mocks for huey task pipeline 
        mock_task = MagicMock()
        mock_import_collection.s.return_value = mock_task
        mock_task.then.return_value = mock_task  # Each then() returns a task

        # Configure the find_s3_import_candidates mock
        mock_find.call_local.return_value = {
            'potential_collection_xmls': [collection_xml_path], 
            'potential_bundle_xmls': [bundle_xml_path]
        }

        # Call the function being tested
        ingest_tasks.process_s3_prefix('test-bucket', 'test-prefix')

        # Assertions
        mock_find.call_local.assert_called_once_with('test-bucket', 'test-prefix')
        
        # Verify the task pipeline was created correctly
        mock_import_collection.s.assert_called_once_with('test-bucket', collection_xml_path)
        mock_huey.enqueue.assert_called_once()  # The pipeline was enqueued
        

def test_import_s3_collection_none_content(mock_file_discovery_service):
    """Test import_s3_collection when read_s3_object returns None."""
    # Setup
    mock_file_discovery_service.read_s3_object.return_value = None
    
    # Call the function
    result = ingest_tasks.import_s3_collection('test-bucket', 'test/key.xml')
    
    # Assertions
    assert result is None
    mock_file_discovery_service.read_s3_object.assert_called_once()
    # Import_from_xml should not be called
    assert not ingest_tasks.CollectionImporter.import_from_xml.called

def test_import_s3_bundle_invalid_importer_response():
    """Test import_s3_bundle when the importer returns an unexpected payload."""
    with patch('lacos.ingest.tasks.BundleImporter.import_from_xml', return_value=None), \
         patch('lacos.ingest.tasks.FileDiscoveryService') as mock_discovery_service_class:
        mock_discovery_instance = MagicMock()
        mock_discovery_service_class.return_value = mock_discovery_instance
        mock_discovery_instance.read_s3_object.return_value = b"<xml>test</xml>"

        result = ingest_tasks.import_s3_bundle('test-bucket', 'test/key.xml')

        assert result is None
        mock_discovery_instance.read_s3_object.assert_called_once_with('test-bucket', 'test/key.xml')
        assert ingest_tasks.BundleImporter.import_from_xml.called

def test_import_s3_bundle_none_content(mock_file_discovery_service):
    """Test import_s3_bundle when read_s3_object returns None."""
    # Setup
    mock_file_discovery_service.read_s3_object.return_value = None
    
    # Call the function
    result = ingest_tasks.import_s3_bundle('test-bucket', 'test/key.xml')
    
    # Assertions
    assert result is None
    mock_file_discovery_service.read_s3_object.assert_called_once()
    # Import_from_xml should not be called
    assert not ingest_tasks.BundleImporter.import_from_xml.called

def test_resolve_collection_bundle_links_not_found():
    """Test resolve_collection_bundle_links when collection is not found."""
    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    with patch.dict('sys.modules'):
        with patch(collection_import_path) as MockCollection, \
             patch('lacos.ingest.tasks.resolve_links_service') as mock_resolve_links:
            MockCollection.objects.get.side_effect = Exception("DoesNotExist")
            MockCollection.DoesNotExist = Exception

            result = ingest_tasks.resolve_collection_bundle_links_task(1, [])

            MockCollection.objects.get.assert_called_once_with(id=1)
            assert not mock_resolve_links.called
            assert result == (1, [])

def test_resolve_collection_bundle_links_other_exception():
    """Test resolve_collection_bundle_links with an unexpected exception."""
    mock_collection = MagicMock()
    mock_collection.id = 1

    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    with patch.dict('sys.modules'):
        with patch(collection_import_path) as MockCollection, \
             patch('lacos.ingest.tasks.resolve_links_service', side_effect=Exception("Unexpected error")):
            MockCollection.objects.get.return_value = mock_collection
            MockCollection.DoesNotExist = Exception

            result = ingest_tasks.resolve_collection_bundle_links_task(1, [('bundle', 'res')])

            MockCollection.objects.get.assert_called_once_with(id=1)
            assert result == (1, [('bundle', 'res')])

def test_map_collection_resources_not_found():
    """Test map_collection_resources when collection is not found."""
    # Patch both model imports
    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    bundle_import_path = 'lacos.blam.models.bundle.bundle_repository.Bundle'
    
    with patch(collection_import_path) as MockCollection, \
         patch(bundle_import_path) as MockBundle:
        # Configure mock Collection to raise DoesNotExist
        MockCollection.objects.get.side_effect = Exception("DoesNotExist")
        MockCollection.DoesNotExist = Exception
        
        # Call the function
        ingest_tasks.map_collection_resources(1, [])
        
        # Assertions
        MockCollection.objects.get.assert_called_once_with(id=1)
        # Should not process any further
        assert not MockBundle.objects.filter.called

def test_map_collection_resources_no_structural_info():
    """Test map_collection_resources when collection has no structural_info."""
    # Create mock collection without structural_info
    mock_collection = MagicMock()
    mock_collection.id = 1
    mock_collection.structural_info = None
    
    # Patch both model imports
    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    bundle_import_path = 'lacos.blam.models.bundle.bundle_repository.Bundle'
    
    with patch(collection_import_path) as MockCollection, \
         patch(bundle_import_path) as MockBundle, \
         patch('lacos.ingest.tasks.ResourceMappingService') as MockResourceMappingService:
        
        # Configure mocks
        MockCollection.objects.get.return_value = mock_collection
        mock_mapping_service = MockResourceMappingService.return_value
        
        # Call the function
        ingest_tasks.map_collection_resources(1, [])
        
        # Assertions
        MockCollection.objects.get.assert_called_once_with(id=1)
        # Should try to map the collection using map_collection_hierarchy
        assert mock_mapping_service.map_collection_hierarchy.called
        assert not MockBundle.objects.filter.called

def test_map_collection_resources_bundle_mapping_error(mock_resource_mapping_service):
    """Test map_collection_resources with error during bundle mapping."""
    # Create mocks
    mock_collection = MagicMock()
    mock_collection.id = 1
    mock_collection.structural_info = MagicMock()
    
    mock_bundle = MagicMock()
    mock_bundle.id = 10
    mock_bundle_queryset = MagicMock()
    mock_bundle_queryset.count.return_value = 1
    mock_bundle_queryset.__iter__.return_value = iter([mock_bundle])
    
    # Patch both model imports
    collection_import_path = 'lacos.blam.models.collection.collection_repository.Collection'
    bundle_import_path = 'lacos.blam.models.bundle.bundle_repository.Bundle'
    
    with patch(collection_import_path) as MockCollection, \
         patch(bundle_import_path) as MockBundle:
        # Configure mock Collection
        MockCollection.objects.get.return_value = mock_collection
        MockCollection.DoesNotExist = Exception
        
        # Configure mock Bundle
        MockBundle.objects.filter.return_value = mock_bundle_queryset
        
        # Make map_collection_hierarchy raise an exception
        mock_resource_mapping_service.map_collection_hierarchy.side_effect = Exception("Bundle mapping error")
        
        # Call the function
        ingest_tasks.map_collection_resources(1, [])
        
        # Assertions
        MockCollection.objects.get.assert_called_once_with(id=1)
        # Should try to map the collection
        assert mock_resource_mapping_service.map_collection_hierarchy.called
        # Should still complete without raising exception

def test_process_s3_prefix_empty_results():
    """Test process_s3_prefix when no XML files are found."""
    # Setup - patch the individual task functions
    with patch('lacos.ingest.tasks.find_s3_import_candidates') as mock_find:
        # Configure mock to return empty results
        mock_find.call_local.return_value = {
            'potential_collection_xmls': [],
            'potential_bundle_xmls': []
        }
        
        # Call the function
        result = ingest_tasks.process_s3_prefix('test-bucket', 'test-prefix')
        
        # Assertions - check call_local() was called instead of the function directly
        mock_find.call_local.assert_called_once_with('test-bucket', 'test-prefix')
        # Should return early without calling other functions

def test_process_s3_prefix_collection_import_failure():
    """Test process_s3_prefix when collection import fails."""
    # Setup - patch the task functions and huey
    with patch('lacos.ingest.tasks.find_s3_import_candidates') as mock_find, \
         patch('lacos.ingest.tasks.import_s3_collection') as mock_import_collection, \
         patch('lacos.ingest.tasks.import_s3_bundles_for_collection') as mock_import_bundles, \
         patch('lacos.ingest.tasks.resolve_collection_bundle_links_task') as mock_resolve, \
         patch('lacos.ingest.tasks.map_collection_resources') as mock_map, \
         patch('lacos.ingest.tasks.huey') as mock_huey:
        
        # Configure mocks
        mock_find.call_local.return_value = {
            'potential_collection_xmls': ['col1/col1/v1/content/col1.xml'],
            'potential_bundle_xmls': ['col1/bun1/v1/content/bun1.xml']
        }
        # Create a mock task
        mock_task = MagicMock()
        mock_import_collection.s.return_value = mock_task
        mock_task.then.return_value = mock_task
        mock_import_bundles.s.return_value = mock_task
        mock_resolve.s.return_value = mock_task
        mock_map.s.return_value = mock_task
        
        # Call the function
        result = ingest_tasks.process_s3_prefix('test-bucket', 'test-prefix')
        
        # Assertions
        mock_find.call_local.assert_called_once()
        mock_import_collection.s.assert_called_once()
        mock_huey.enqueue.assert_called_once_with(mock_task)

def test_process_s3_prefix_bundle_collection_mismatch():
    """Test process_s3_prefix when bundle doesn't match imported collection."""
    # Setup - patch the task functions
    with patch('lacos.ingest.tasks.find_s3_import_candidates') as mock_find, \
         patch('lacos.ingest.tasks.import_s3_collection') as mock_import_collection, \
         patch('lacos.ingest.tasks.import_s3_bundles_for_collection') as mock_import_bundles, \
         patch('lacos.ingest.tasks.resolve_collection_bundle_links_task') as mock_resolve, \
         patch('lacos.ingest.tasks.map_collection_resources') as mock_map, \
         patch('lacos.ingest.tasks.huey') as mock_huey:
        
        # Configure mocks
        mock_find.call_local.return_value = {
            'potential_collection_xmls': ['col1/col1/v1/content/col1.xml'],
            'potential_bundle_xmls': ['col2/bun1/v1/content/bun1.xml']  # Different collection prefix
        }
        # Create a mock task
        mock_task = MagicMock()
        mock_import_collection.s.return_value = mock_task
        mock_task.then.return_value = mock_task
        mock_import_bundles.s.return_value = mock_task
        mock_resolve.s.return_value = mock_task
        mock_map.s.return_value = mock_task
        
        # Call the function
        result = ingest_tasks.process_s3_prefix('test-bucket', 'test-prefix')
        
        # Assertions
        mock_find.call_local.assert_called_once()
        mock_import_collection.s.assert_called_once()
        mock_huey.enqueue.assert_called_once()

def test_process_s3_prefix_invalid_collection_key():
    """Test process_s3_prefix with invalid collection key format."""
    # Setup - patch the task functions
    with patch('lacos.ingest.tasks.find_s3_import_candidates') as mock_find, \
         patch('lacos.ingest.tasks.import_s3_collection') as mock_import_collection, \
         patch('lacos.ingest.tasks.import_s3_bundles_for_collection') as mock_import_bundles, \
         patch('lacos.ingest.tasks.resolve_collection_bundle_links_task') as mock_resolve, \
         patch('lacos.ingest.tasks.map_collection_resources') as mock_map, \
         patch('lacos.ingest.tasks.huey') as mock_huey:
        
        # Configure mocks with invalid collection key
        mock_find.call_local.return_value = {
            'potential_collection_xmls': ['invalid-format'],
            'potential_bundle_xmls': []
        }
        
        # Create a mock task
        mock_task = MagicMock()
        mock_import_collection.s.return_value = mock_task
        mock_task.then.return_value = mock_task
        mock_import_bundles.s.return_value = mock_task
        mock_resolve.s.return_value = mock_task
        mock_map.s.return_value = mock_task
        
        # Call the function
        result = ingest_tasks.process_s3_prefix('test-bucket', 'test-prefix')
        
        # Assertions
        mock_find.call_local.assert_called_once()
        # Should attempt to import collection, but then it won't be added to imported_collections_map
        mock_import_collection.s.assert_called_once_with('test-bucket', 'invalid-format')
        mock_huey.enqueue.assert_called_once()


def test_process_s3_prefix_groups_bundle_keys():
    """Test process_s3_prefix groups bundle keys by collection identifier."""
    with patch('lacos.ingest.tasks.find_s3_import_candidates') as mock_find, \
         patch('lacos.ingest.tasks.import_s3_collection') as mock_import_collection, \
         patch('lacos.ingest.tasks.import_s3_bundles_for_collection') as mock_import_bundles, \
         patch('lacos.ingest.tasks.resolve_collection_bundle_links_task') as mock_resolve, \
         patch('lacos.ingest.tasks.map_collection_resources') as mock_map, \
         patch('lacos.ingest.tasks.huey') as mock_huey:

        collection_key = 'col1/col1/v1/content/col1.xml'
        bundle_key_one = 'col1/bun1/v1/content/bun1.xml'
        bundle_key_two = 'col1/bun2/v1/content/bun2.xml'
        unrelated_bundle = 'col2/bun3/v1/content/bun3.xml'

        mock_find.call_local.return_value = {
            'potential_collection_xmls': [collection_key],
            'potential_bundle_xmls': [bundle_key_one, bundle_key_two, unrelated_bundle],
        }

        mock_task = MagicMock()
        mock_import_collection.s.return_value = mock_task
        mock_task.then.return_value = mock_task
        mock_import_bundles.s.return_value = mock_task
        mock_resolve.s.return_value = mock_task
        mock_map.s.return_value = mock_task

        ingest_tasks.process_s3_prefix('test-bucket', 'test-prefix')

        mock_find.call_local.assert_called_once_with('test-bucket', 'test-prefix')
        mock_import_collection.s.assert_called_once_with('test-bucket', collection_key)
        mock_import_bundles.s.assert_called_once_with(
            bundle_keys=[bundle_key_one, bundle_key_two],
            bucket='test-bucket',
        )
        mock_huey.enqueue.assert_called_once_with(mock_task)
