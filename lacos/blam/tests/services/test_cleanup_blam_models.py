import pytest
from unittest.mock import patch, MagicMock
from io import StringIO
from django.core.management import call_command


from lacos.blam.models.collection.collection_repository import Collection



@pytest.fixture
def command_output():
    """Capture command output for testing."""
    out = StringIO()
    err = StringIO()
    return out, err


@pytest.fixture
def mock_cleanup_service():
    """Mock the CleanupService methods."""
    with patch('lacos.blam.services.cleanup_service.CleanupService') as mock_service:
        # Setup successful resource cleanup mock
        mock_service.cleanup_bundle_resources.return_value = {
            'bundles_without_resources': 3,
            'orphaned_resources_removed': 2,
            'empty_resource_containers': 1,
            'orphaned_media_removed': 5,
            'orphaned_written_removed': 3,
            'orphaned_other_removed': 2,
            'fixed_resources': 8,
            'errors': []
        }
        
        # Setup successful link cleanup mock
        mock_service.fix_collection_bundle_links.return_value = {
            'fixed_links': 4,
            'errors': []
        }
        
        # Setup successful header cleanup mock
        mock_service.cleanup_orphaned_headers = MagicMock(return_value={
            'orphaned_headers_removed': 3,
            'fixed_headers': 2,
            'errors': []
        })
        
        # Setup successful publication info cleanup mock
        mock_service.cleanup_orphaned_publication_info = MagicMock(return_value={
            'orphaned_publication_info_removed': 5,
            'fixed_publication_info': 1,
            'errors': []
        })
        
        yield mock_service


@pytest.fixture
def mock_empty_database():
    """Setup empty mock database for dry run tests."""
    with patch('lacos.blam.models.bundle.bundle_repository.Bundle.objects') as bundle_mock, \
         patch('lacos.blam.models.bundle.bundle_structural_info.BundleResources.objects') as resources_mock, \
         patch('lacos.blam.models.bundle.bundle_structural_info.MediaResource.objects') as media_mock, \
         patch('lacos.blam.models.bundle.bundle_structural_info.WrittenResource.objects') as written_mock, \
         patch('lacos.blam.models.bundle.bundle_structural_info.OtherResource.objects') as other_mock, \
         patch('lacos.blam.models.collection.collection_repository.Collection.objects') as collection_mock, \
         patch('lacos.blam.models.collection.collection_header.CollectionHeader.objects') as header_mock, \
         patch('lacos.blam.models.collection.collection_publication_info.CollectionPublicationInfo.objects') as publication_mock:
        
        # Mock filter results for bundles
        bundle_filter_mock = MagicMock()
        bundle_filter_mock.count.return_value = 2
        bundle_mock.filter.return_value = bundle_filter_mock
        
        # Mock filter results for resources
        resources_filter_mock = MagicMock()
        resources_filter_mock.count.return_value = 3
        resources_mock.filter.return_value = resources_filter_mock
        
        # Mock annotate and filter for empty resources
        resources_annotate_mock = MagicMock()
        empty_resources_mock = MagicMock()
        empty_resources_mock.count.return_value = 1
        resources_annotate_mock.filter.return_value = empty_resources_mock
        resources_mock.annotate.return_value = resources_annotate_mock
        
        # Mock filter results for orphaned resources
        media_filter_mock = MagicMock()
        media_filter_mock.count.return_value = 4
        media_mock.filter.return_value = media_filter_mock
        
        written_filter_mock = MagicMock()
        written_filter_mock.count.return_value = 2
        written_mock.filter.return_value = written_filter_mock
        
        other_filter_mock = MagicMock()
        other_filter_mock.count.return_value = 1
        other_mock.filter.return_value = other_filter_mock
        
        # Mock collection relationships for links
        collection_mock.all.return_value = []
        
        # Mock orphaned headers
        header_filter_mock = MagicMock()
        header_filter_mock.count.return_value = 3
        header_mock.filter.return_value = header_filter_mock
        
        # Mock orphaned publication info
        publication_filter_mock = MagicMock()
        publication_filter_mock.count.return_value = 5
        publication_mock.filter.return_value = publication_filter_mock
        
        yield


def test_cleanup_command_default(command_output, mock_cleanup_service):
    """Test the cleanup command with default options."""
    out, err = command_output
    
    call_command('cleanup_blam_models', stdout=out, stderr=err)
    
    # Check that both cleanup methods were called
    mock_cleanup_service.cleanup_bundle_resources.assert_called_once()
    mock_cleanup_service.fix_collection_bundle_links.assert_called_once()
    
    # Check output includes both cleanup operations
    output = out.getvalue()
    assert "Cleaning up bundle resources" in output
    assert "Cleaning up collection-bundle links" in output
    assert "Database cleanup completed" in output
    assert "12 issues fixed" in output  # 8 resources + 4 links


def test_cleanup_command_resources_only(command_output, mock_cleanup_service):
    """Test the cleanup command with --resources-only flag."""
    out, err = command_output
    
    call_command('cleanup_blam_models', '--resources-only', stdout=out, stderr=err)
    
    # Check that only resource cleanup was called
    mock_cleanup_service.cleanup_bundle_resources.assert_called_once()
    mock_cleanup_service.fix_collection_bundle_links.assert_not_called()
    
    # Check output includes only resource cleanup
    output = out.getvalue()
    assert "Cleaning up bundle resources" in output
    assert "Cleaning up collection-bundle links" not in output
    assert "Database cleanup completed" in output
    assert "8 issues fixed" in output  # Only 8 resources


def test_cleanup_command_links_only(command_output, mock_cleanup_service):
    """Test the cleanup command with --links-only flag."""
    out, err = command_output
    
    call_command('cleanup_blam_models', '--links-only', stdout=out, stderr=err)
    
    # Check that only link cleanup was called
    mock_cleanup_service.cleanup_bundle_resources.assert_not_called()
    mock_cleanup_service.fix_collection_bundle_links.assert_called_once()
    
    # Check output includes only link cleanup
    output = out.getvalue()
    assert "Cleaning up bundle resources" not in output
    assert "Cleaning up collection-bundle links" in output
    assert "Database cleanup completed" in output
    assert "4 issues fixed" in output  # Only 4 links


def test_cleanup_command_dry_run(command_output, mock_empty_database):
    """Test the cleanup command with --dry-run flag."""
    out, err = command_output
    
    with patch('builtins.input', return_value='n'):  # Skip any potential prompts
        call_command('cleanup_blam_models', '--dry-run', stdout=out, stderr=err)
    
    # Check that output includes dry run message
    output = out.getvalue()
    assert "DRY RUN MODE - No changes will be made" in output
    assert "Dry run completed" in output
    assert "13 issues found that would be fixed" in output  # Total from the mock data


def test_cleanup_command_with_errors(command_output, mock_cleanup_service):
    """Test the cleanup command with errors in results."""
    out, err = command_output
    
    # Mock error results from service
    mock_cleanup_service.cleanup_bundle_resources.return_value['errors'] = ['Error 1', 'Error 2']
    mock_cleanup_service.fix_collection_bundle_links.return_value['errors'] = ['Error 3']
    
    exit_code = call_command('cleanup_blam_models', stdout=out, stderr=err)
    
    # Check output includes error reporting
    output = out.getvalue()
    assert "Errors: 2" in output
    assert "Error 1" in output
    assert "Error 2" in output
    assert "Errors: 1" in output
    assert "Error 3" in output
    assert "Errors were encountered during cleanup" in output


@patch('builtins.input', return_value='y')
def test_cleanup_resources_real_database(mock_input, command_output):
    """Test a more realistic database setup for bundle resources cleanup."""
    # This test uses patch decorators for input and doesn't use the mock fixtures
    # to provide a more realistic test with database setup
    out, err = command_output
    
    with patch('lacos.blam.models.bundle.bundle_repository.Bundle.objects') as bundle_mock, \
         patch('lacos.blam.services.cleanup_service.CleanupService') as service_mock:
        
        # Setup realistic bundle query responses
        bundle_filter_mock = MagicMock()
        bundle_filter_mock.count.return_value = 3
        bundle_mock.filter.return_value = bundle_filter_mock
        
        # Mock the actual cleanup service call
        service_mock.cleanup_bundle_resources.return_value = {
            'bundles_without_resources': 3,
            'fixed_resources': 3,
            'orphaned_resources_removed': 0,
            'empty_resource_containers': 0,
            'orphaned_media_removed': 0,
            'orphaned_written_removed': 0,
            'orphaned_other_removed': 0,
            'errors': []
        }
        
        # Call with resources-only to focus the test
        call_command('cleanup_blam_models', '--resources-only', stdout=out, stderr=err)
        
        # Verify service was called correctly
        service_mock.cleanup_bundle_resources.assert_called_once()
        
        # Check output includes success message
        output = out.getvalue()
        assert "Fixed resources: 3" in output
        assert "Bundles without resources: 3" in output
        assert "Database cleanup completed" in output


@patch('builtins.input', return_value='y')
def test_cleanup_links_real_database(mock_input, command_output):
    """Test a more realistic database setup for collection-bundle links cleanup."""
    # This test uses patch decorators for input and doesn't use the mock fixtures
    # to provide a more realistic test with database setup
    out, err = command_output
    
    with patch('lacos.blam.models.collection.collection_repository.Collection.objects') as collection_mock, \
         patch('lacos.blam.services.cleanup_service.CleanupService') as service_mock:
        
        # Setup mock collections with incorrect links
        collection1 = MagicMock(spec=Collection)
        collection1.id = 1
        collection1.bundle_collection.all.return_value = []
        
        collection_mock.all.return_value = [collection1]
        
        # Mock the actual cleanup service call
        service_mock.fix_collection_bundle_links.return_value = {
            'fixed_links': 2,
            'errors': []
        }
        
        # Call with links-only to focus the test
        call_command('cleanup_blam_models', '--links-only', stdout=out, stderr=err)
        
        # Verify service was called correctly
        service_mock.fix_collection_bundle_links.assert_called_once()
        
        # Check output includes success message
        output = out.getvalue()
        assert "Fixed links: 2" in output
        assert "Database cleanup completed" in output


def test_cleanup_orphaned_headers(command_output, mock_cleanup_service):
    """Test cleaning up orphaned collection headers."""
    out, err = command_output
    
    # Add --headers-only option to focus just on headers
    call_command('cleanup_blam_models', '--headers-only', stdout=out, stderr=err)
    
    # Check that only header cleanup was called
    mock_cleanup_service.cleanup_orphaned_headers.assert_called_once()
    mock_cleanup_service.cleanup_bundle_resources.assert_not_called()
    mock_cleanup_service.fix_collection_bundle_links.assert_not_called()
    mock_cleanup_service.cleanup_orphaned_publication_info.assert_not_called()
    
    # Check output includes header cleanup
    output = out.getvalue()
    assert "Cleaning up orphaned collection headers" in output
    assert "Orphaned headers removed: 3" in output
    assert "Fixed headers: 2" in output
    assert "Database cleanup completed" in output
    assert "5 issues fixed" in output  # 3 removed + 2 fixed


def test_cleanup_orphaned_publication_info(command_output, mock_cleanup_service):
    """Test cleaning up orphaned publication info records."""
    out, err = command_output
    
    # Add --publication-info-only option to focus just on publication info
    call_command('cleanup_blam_models', '--publication-info-only', stdout=out, stderr=err)
    
    # Check that only publication info cleanup was called
    mock_cleanup_service.cleanup_orphaned_publication_info.assert_called_once()
    mock_cleanup_service.cleanup_bundle_resources.assert_not_called()
    mock_cleanup_service.fix_collection_bundle_links.assert_not_called()
    mock_cleanup_service.cleanup_orphaned_headers.assert_not_called()
    
    # Check output includes publication info cleanup
    output = out.getvalue()
    assert "Cleaning up orphaned publication info records" in output
    assert "Orphaned publication info records removed: 5" in output
    assert "Fixed publication info records: 1" in output
    assert "Database cleanup completed" in output
    assert "6 issues fixed" in output  # 5 removed + 1 fixed


@patch('builtins.input', return_value='y')
def test_cleanup_all_metadata_dry_run(mock_input, command_output, mock_empty_database):
    """Test dry run for cleaning up all metadata (headers and publication info)."""
    out, err = command_output
    
    with patch('lacos.blam.models.collection.collection_header.CollectionHeader.objects.filter') as header_mock, \
         patch('lacos.blam.models.collection.collection_publication_info.CollectionPublicationInfo.objects.filter') as publication_mock:
        
        # Setup mock query results
        header_mock.return_value.count.return_value = 3
        publication_mock.return_value.count.return_value = 5
        
        # Run dry run with metadata-only option
        call_command('cleanup_blam_models', '--metadata-only', '--dry-run', stdout=out, stderr=err)
        
        # Check output includes expected counts
        output = out.getvalue()
        assert "DRY RUN MODE - No changes will be made" in output
        assert "Orphaned collection headers found: 3" in output
        assert "Orphaned publication info records found: 5" in output
        assert "Dry run completed. 8 issues found that would be fixed" in output
