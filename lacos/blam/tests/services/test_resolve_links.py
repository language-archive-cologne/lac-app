import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
import logging

from lacos.blam.services.resolve_links import (
    resolve_collection_bundle_links,
    get_collection_by_id,
    resolve_bundle_links_primary_method,
    get_bundle_structural_infos,
    resolve_links_using_structural_infos
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter

# Import required models only for typing/reference
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.base_project_info import ProjectInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo

# Disable logger during tests to avoid noise
logging.getLogger('lacos.blam.services.resolve_links').setLevel(logging.CRITICAL)


# Simple tests for get_collection_by_id
def test_get_collection_by_id_none():
    """Test get_collection_by_id handles None value correctly."""
    assert get_collection_by_id(None) is None


def test_get_collection_by_id_not_found(monkeypatch):
    """Test get_collection_by_id handles non-existent IDs correctly."""
    collection_id = uuid4()
    
    # Mock Collection.objects.get to raise DoesNotExist
    def mock_get(**kwargs):
        raise Collection.DoesNotExist("Test exception")
    
    monkeypatch.setattr(Collection.objects, 'get', mock_get)
    
    assert get_collection_by_id(collection_id) is None


def test_get_collection_by_id_found(monkeypatch):
    """Test get_collection_by_id returns collection when found."""
    collection_id = uuid4()
    
    # Create a mock collection
    mock_collection = MagicMock(spec=Collection)
    mock_collection.id = collection_id
    
    # Mock Collection.objects.get to return our mock
    def mock_get(**kwargs):
        assert kwargs.get('id') == collection_id
        return mock_collection
    
    monkeypatch.setattr(Collection.objects, 'get', mock_get)
    
    # Test the function
    result = get_collection_by_id(collection_id)
    assert result is mock_collection


def test_get_collection_by_id_exception(monkeypatch):
    """Test get_collection_by_id handles other exceptions gracefully."""
    collection_id = uuid4()
    
    # Mock Collection.objects.get to raise generic exception
    def mock_get(**kwargs):
        raise Exception("Test exception")
    
    monkeypatch.setattr(Collection.objects, 'get', mock_get)
    
    assert get_collection_by_id(collection_id) is None


# Tests for resolve_bundle_links_primary_method
@patch('lacos.blam.services.resolve_links.CollectionImporter')
def test_resolve_bundle_links_primary_method_success(mock_importer_class):
    """Test resolve_bundle_links_primary_method returns value from CollectionImporter."""
    # Create a mock collection
    mock_collection = MagicMock()
    
    # Setup the mock class method to return a value
    mock_importer_class.resolve_bundle_references.return_value = 3
    
    # Test the function
    result = resolve_bundle_links_primary_method(mock_collection)
    assert result == 3
    
    # Verify the mock was called correctly
    mock_importer_class.resolve_bundle_references.assert_called_once_with(mock_collection)


@patch('lacos.blam.services.resolve_links.CollectionImporter')
def test_resolve_bundle_links_primary_method_attribute_error(mock_importer_class):
    """Test resolve_bundle_links_primary_method propagates AttributeError."""
    # Create a mock collection
    mock_collection = MagicMock()
    
    # Setup the mock to raise AttributeError
    mock_importer_class.resolve_bundle_references.side_effect = AttributeError("Test error")
    
    # Test the function
    with pytest.raises(AttributeError):
        resolve_bundle_links_primary_method(mock_collection)
    
    # Verify the mock was called correctly
    mock_importer_class.resolve_bundle_references.assert_called_once_with(mock_collection)


@patch('lacos.blam.services.resolve_links.CollectionImporter')
def test_resolve_bundle_links_primary_method_exception(mock_importer_class):
    """Test resolve_bundle_links_primary_method propagates general exceptions."""
    # Create a mock collection
    mock_collection = MagicMock()
    
    # Setup the mock to raise Exception
    mock_importer_class.resolve_bundle_references.side_effect = Exception("Test error")
    
    # Test the function
    with pytest.raises(Exception):
        resolve_bundle_links_primary_method(mock_collection)
    
    # Verify the mock was called correctly
    mock_importer_class.resolve_bundle_references.assert_called_once_with(mock_collection)


# Tests for get_bundle_structural_infos
def test_get_bundle_structural_infos_empty():
    """Test get_bundle_structural_infos with empty bundle_collection."""
    # Create a mock collection with empty bundle_collection
    mock_collection = MagicMock(spec=Collection)
    mock_collection.bundle_collection.all.return_value = []
    
    # Test the function
    result = get_bundle_structural_infos(mock_collection)
    assert result == []
    # Verify the mock was called correctly
    mock_collection.bundle_collection.all.assert_called_once()


def test_get_bundle_structural_infos_with_bundles():
    """Test get_bundle_structural_infos with bundle_collection containing items."""
    # Create mock structural info objects (without spec constraint)
    mock_info1 = MagicMock()
    mock_info2 = MagicMock()
    
    # Create mock collection with bundle_collection containing the mock infos
    mock_collection = MagicMock(spec=Collection)
    mock_collection.bundle_collection.all.return_value = [mock_info1, mock_info2]
    
    # Test the function
    result = get_bundle_structural_infos(mock_collection)
    assert result == [mock_info1, mock_info2]
    # Verify the mock was called correctly
    mock_collection.bundle_collection.all.assert_called_once()


def test_get_bundle_structural_infos_exception():
    """Test get_bundle_structural_infos handles exceptions gracefully."""
    # Create a mock collection that raises exception on bundle_collection.all()
    mock_collection = MagicMock(spec=Collection)
    mock_collection.bundle_collection.all.side_effect = Exception("Test error")
    
    # Test the function
    result = get_bundle_structural_infos(mock_collection)
    assert result == []
    # Verify the mock was called correctly
    mock_collection.bundle_collection.all.assert_called_once()


# Tests for resolve_links_using_structural_infos
def test_resolve_links_using_structural_infos_no_methods():
    """Test resolve_links_using_structural_infos with objects lacking resolve_bundle."""
    # Create mock structural info objects without resolve_bundle (no spec)
    mock_info1 = MagicMock()
    mock_info2 = MagicMock()
    
    # Remove resolve_bundle method from mocks
    del mock_info1.resolve_bundle
    del mock_info2.resolve_bundle
    
    # Setup to test bundle property too
    mock_info1.bundle = MagicMock()
    del mock_info1.bundle.resolve_bundle
    mock_info2.bundle = MagicMock()
    del mock_info2.bundle.resolve_bundle
    
    # Give IDs for error message generation
    mock_info1.id = "info1"
    mock_info2.id = "info2"
    
    # Test the function
    count, errors = resolve_links_using_structural_infos([mock_info1, mock_info2])
    assert count == 0
    assert len(errors) == 2  # Should have one error for each info object


def test_resolve_links_using_structural_infos_with_method():
    """Test resolve_links_using_structural_infos with objects having resolve_bundle."""
    # Create mock structural info objects with resolve_bundle (no spec)
    mock_info1 = MagicMock()
    mock_info2 = MagicMock()
    
    # Set up resolve_bundle to return different values
    mock_info1.resolve_bundle.return_value = True
    mock_info2.resolve_bundle.return_value = False
    
    # Test the function
    count, errors = resolve_links_using_structural_infos([mock_info1, mock_info2])
    assert count == 2  # Both methods are called and counted, even if one returns False
    assert len(errors) == 0  # No errors when methods exist
    
    # Verify the mocks were called correctly
    mock_info1.resolve_bundle.assert_called_once()
    mock_info2.resolve_bundle.assert_called_once()


def test_resolve_links_using_structural_infos_bundle_method():
    """Test resolve_links_using_structural_infos with bundle.resolve_bundle fallback."""
    # Create mock structural info without resolve_bundle but with bundle that has it
    mock_info = MagicMock()
    del mock_info.resolve_bundle
    
    # Mock the bundle with resolve_bundle method
    mock_bundle = MagicMock()
    mock_bundle.resolve_bundle.return_value = True
    mock_info.bundle = mock_bundle
    mock_info.id = "info"
    
    # Test the function
    count, errors = resolve_links_using_structural_infos([mock_info])
    assert count == 1
    assert len(errors) == 0
    
    # Verify the mock was called correctly
    mock_bundle.resolve_bundle.assert_called_once()


def test_resolve_links_using_structural_infos_method_exception():
    """Test resolve_links_using_structural_infos handles exceptions in resolve_bundle."""
    # Create mock structural info with resolve_bundle that raises exception
    mock_info = MagicMock()
    mock_info.resolve_bundle.side_effect = Exception("Test error")
    mock_info.id = "info"
    
    # Test the function
    count, errors = resolve_links_using_structural_infos([mock_info])
    assert count == 0
    assert len(errors) == 1
    
    # Verify the mock was called correctly
    mock_info.resolve_bundle.assert_called_once()


# Tests for main resolve_collection_bundle_links function
def test_resolve_collection_bundle_links_none():
    """Test resolve_collection_bundle_links with None collection_id."""
    result = resolve_collection_bundle_links(None)
    assert result is None


def test_resolve_collection_bundle_links_not_found(monkeypatch):
    """Test resolve_collection_bundle_links with get_collection_by_id returning None."""
    collection_id = uuid4()
    
    # Mock get_collection_by_id to return None
    def mock_get_collection(coll_id):
        assert coll_id == collection_id
        return None
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.get_collection_by_id', mock_get_collection)
    
    # Test the function
    result = resolve_collection_bundle_links(collection_id)
    assert result is None


def test_resolve_collection_bundle_links_primary_method(monkeypatch):
    """Test resolve_collection_bundle_links with successful primary method."""
    collection_id = uuid4()
    mock_collection = MagicMock(spec=Collection)
    
    # Mock get_collection_by_id to return our mock collection
    def mock_get_collection(coll_id):
        assert coll_id == collection_id
        return mock_collection
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.get_collection_by_id', mock_get_collection)
    
    # Mock resolve_bundle_links_primary_method to return a success count
    def mock_primary_method(coll):
        assert coll is mock_collection
        return 5  # Successfully resolved 5 links
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.resolve_bundle_links_primary_method', mock_primary_method)
    
    # Test the function
    result = resolve_collection_bundle_links(collection_id)
    assert result == collection_id


def test_resolve_collection_bundle_links_fallback(monkeypatch):
    """Test resolve_collection_bundle_links fallback when primary method fails."""
    collection_id = uuid4()
    mock_collection = MagicMock(spec=Collection)
    mock_infos = [MagicMock()]  # No spec
    
    # Mock get_collection_by_id to return our mock collection
    def mock_get_collection(coll_id):
        return mock_collection
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.get_collection_by_id', mock_get_collection)
    
    # Mock resolve_bundle_links_primary_method to raise AttributeError
    def mock_primary_method(coll):
        raise AttributeError("Test error")
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.resolve_bundle_links_primary_method', mock_primary_method)
    
    # Mock get_bundle_structural_infos to return mock infos
    def mock_get_infos(coll):
        assert coll is mock_collection
        return mock_infos
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.get_bundle_structural_infos', mock_get_infos)
    
    # Mock resolve_links_using_structural_infos
    def mock_resolve_links(infos):
        assert infos is mock_infos
        return 3, []  # Successfully resolved 3 links with no errors
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.resolve_links_using_structural_infos', mock_resolve_links)
    
    # Test the function
    result = resolve_collection_bundle_links(collection_id)
    assert result == collection_id


def test_resolve_collection_bundle_links_fallback_exception(monkeypatch):
    """Test resolve_collection_bundle_links when primary method raises generic exception."""
    collection_id = uuid4()
    mock_collection = MagicMock(spec=Collection)
    mock_infos = [MagicMock()]  # No spec
    
    # Mock get_collection_by_id to return our mock collection
    def mock_get_collection(coll_id):
        return mock_collection
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.get_collection_by_id', mock_get_collection)
    
    # Mock resolve_bundle_links_primary_method to raise Exception
    def mock_primary_method(coll):
        raise Exception("Test error")
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.resolve_bundle_links_primary_method', mock_primary_method)
    
    # Mock get_bundle_structural_infos to return mock infos
    def mock_get_infos(coll):
        assert coll is mock_collection
        return mock_infos
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.get_bundle_structural_infos', mock_get_infos)
    
    # Mock resolve_links_using_structural_infos
    def mock_resolve_links(infos):
        assert infos is mock_infos
        return 2, []  # Successfully resolved 2 links with no errors
    
    monkeypatch.setattr('lacos.blam.services.resolve_links.resolve_links_using_structural_infos', mock_resolve_links)
    
    # Test the function
    result = resolve_collection_bundle_links(collection_id)
    assert result == collection_id
