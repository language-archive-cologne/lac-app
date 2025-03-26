import pytest
from unittest.mock import patch, MagicMock
import os

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_structural_info import import_structural_info
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
    CollectionAdditionalMetadataFile,
    CollectionHasCollectionMember
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation
)
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.base_project_info import ProjectInfo
from blam_schemas.collection.blam_collection_repository_v1_0 import (
    CollectionHasCollectionMemberIdentifierType
)


@pytest.fixture
def real_collection_xml():
    """Get the XML content from a real collection file in the data directory."""
    xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        alternate_paths = [
            os.path.join('data', 'algerien', 'v1', 'content', 'algerien.xml'),
            os.path.join('data', 'formatted', 'algerien.xml')
        ]
        for path in alternate_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                continue
        
        raise FileNotFoundError(f"Could not find collection XML file at {xml_path} or alternate locations")


@pytest.fixture
def real_cmd_data(real_collection_xml):
    """Parse real collection XML into CMD data"""
    with patch('django.core.exceptions.ValidationError', Exception):
        return CollectionImporter.validate_xml(real_collection_xml)


@pytest.fixture
def mock_metadata_file():
    """Create a mock metadata file with configurable fields"""
    def create_metadata_file(
        file_name="metadata.xml",
        file_pid="hdl:11341/0000-0000-0000-3D7C",
        mime_type="application/xml",
        is_metadata_for="collection",
        file_description=None
    ):
        metadata_file = type('MetadataFile', (), {
            'file_name': file_name,
            'file_pid': file_pid,
            'mime_type': mime_type,
            'is_metadata_for': is_metadata_for,
            'file_description': file_description
        })
        return metadata_file
    return create_metadata_file


@pytest.fixture
def mock_collection_member():
    """Create a mock collection member with configurable fields"""
    def create_member(identifier="hdl:11341/0000-0000-0000-3D7E", identifier_type=CollectionHasCollectionMemberIdentifierType.HANDLE):
        member = type('Member', (), {
            'value': identifier,
            'identifier_type': identifier_type
        })
        return member
    return create_member


@pytest.fixture
def mock_structural_info():
    """Create a mock structural info schema with configurable fields"""
    def create_struct_info(metadata_files=None, members=None):
        struct_info = type('StructuralInfo', (), {
            'collection_additional_metadata_file': metadata_files or [],
            'collection_members': type('Members', (), {
                'collection_has_collection_member': members or []
            })() if members else None
        })
        return struct_info
    return create_struct_info


@pytest.fixture
def mock_cmd_data(mock_structural_info):
    """Create a mock CMD data with configurable structural info"""
    def create_cmd(struct_info):
        return type('Cmd', (), {
            'components': type('Components', (), {
                'blam_collection_repository_v1_0': type('Repo', (), {
                    'collection_structural_info': struct_info
                })()
            })()
        })()
    return create_cmd


@pytest.fixture
def mock_collection():
    """Create a Collection instance for testing"""
    # Create mock objects
    header = MagicMock()
    location = MagicMock()
    general_info = MagicMock(display_title="Test Collection", location=location)
    publication_info = MagicMock(publication_year=2024, data_provider="Test Provider")
    project_info = MagicMock()
    admin_info = MagicMock(availability_date="2024-01-01")
    
    # Create the mock collection
    collection = MagicMock(
        base_header=header,
        general_info=general_info,
        publication_info=publication_info,
        project_info=project_info,
        administrative_info=admin_info,
        structural_info=None  # This is allowed to be None as per the model
    )
    
    return collection


@pytest.fixture
def mock_orm_operations():
    """Mock Django ORM operations"""
    # Create mock objects for each model operation
    structural_info = MagicMock()
    structural_info.members = MagicMock()
    structural_info.additional_metadata_files = MagicMock()
    
    metadata_file = MagicMock()
    member = MagicMock()
    
    # Mock get_or_create operations
    with patch('lacos.blam.models.collection.collection_structural_info.CollectionStructuralInfo.objects.get_or_create') as mock_structural_get_or_create, \
         patch('lacos.blam.models.collection.collection_structural_info.CollectionAdditionalMetadataFile.objects.get_or_create') as mock_metadata_get_or_create, \
         patch('lacos.blam.models.collection.collection_structural_info.CollectionHasCollectionMember.objects.create') as mock_member_create:
        
        # Set up return values
        mock_structural_get_or_create.return_value = (structural_info, True)
        mock_metadata_get_or_create.return_value = (metadata_file, True)
        mock_member_create.return_value = member
        
        yield {
            'structural_info': structural_info,
            'metadata_file': metadata_file,
            'member': member,
            'mock_structural_get_or_create': mock_structural_get_or_create,
            'mock_metadata_get_or_create': mock_metadata_get_or_create,
            'mock_member_create': mock_member_create
        }


@pytest.mark.django_db
@pytest.fixture
def mock_collection():
    """Create a Collection instance for testing"""
    # Create mock objects
    header = MagicMock()
    location = MagicMock()
    general_info = MagicMock(display_title="Test Collection", location=location)
    publication_info = MagicMock(publication_year=2024, data_provider="Test Provider")
    project_info = MagicMock()
    admin_info = MagicMock(availability_date="2024-01-01")
    
    # Create the mock collection
    collection = MagicMock(
        base_header=header,
        general_info=general_info,
        publication_info=publication_info,
        project_info=project_info,
        administrative_info=admin_info,
        structural_info=None  # This is allowed to be None as per the model
    )
    
    return collection


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the structural info from CMD data
    struct_info = real_cmd_data.components.blam_collection_repository_v1_0.collection_structural_info
    
    # Verify collection members
    assert hasattr(struct_info, 'collection_members')
    assert struct_info.collection_members is not None
    members = struct_info.collection_members.collection_has_collection_member
    assert len(members) == 26  # Real data has 26 members
    
    # Verify first member
    first_member = members[0]
    assert first_member.value == "hdl:11341/0000-0000-0000-3D7E"
    assert first_member.identifier_type == CollectionHasCollectionMemberIdentifierType.HANDLE
    
    # Verify last member
    last_member = members[-1]
    assert last_member.value == "hdl:11341/0000-0000-0000-3DBF"
    assert last_member.identifier_type == CollectionHasCollectionMemberIdentifierType.HANDLE


@pytest.mark.django_db
def test_structural_info_data_mapping(real_cmd_data, mock_collection, mock_orm_operations):
    """Test that structural info is mapped correctly from CMD to Django model"""
    # Test import with real data
    struct_info = import_structural_info(real_cmd_data, mock_collection)
    
    # Verify that get_or_create was called with the correct collection
    mock_orm_operations['mock_structural_get_or_create'].assert_called_once_with(collection=mock_collection)
    
    # Verify that the structural info was returned
    assert struct_info == mock_orm_operations['structural_info']


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data, mock_collection, mock_orm_operations):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    struct_info1 = import_structural_info(real_cmd_data, mock_collection)
    
    # Second import
    struct_info2 = import_structural_info(real_cmd_data, mock_collection)
    
    # Verify that get_or_create was called twice with the same parameters
    assert mock_orm_operations['mock_structural_get_or_create'].call_count == 2
    assert struct_info1 == struct_info2


@pytest.mark.django_db
def test_member_ordering(real_cmd_data, mock_collection, mock_orm_operations):
    """Test that collection members maintain their order from the XML"""
    # Import the data
    struct_info = import_structural_info(real_cmd_data, mock_collection)
    
    # Verify that members were created with the correct order
    calls = mock_orm_operations['mock_member_create'].call_args_list
    for i, call in enumerate(calls):
        assert call.kwargs['order'] == i


@pytest.mark.django_db
def test_missing_data_handling(mock_collection, mock_orm_operations):
    """Test handling of missing data"""
    # Create a minimal CMD data structure
    cmd_data = type('Cmd', (), {
        'components': type('Components', (), {
            'blam_collection_repository_v1_0': type('Repo', (), {
                'collection_structural_info': type('StructuralInfo', (), {
                    'collection_additional_metadata_file': [],
                    'collection_members': None
                })()
            })()
        })()
    })()
    
    # Import should still work with missing data
    result = import_structural_info(cmd_data, mock_collection)
    
    # Verify that get_or_create was called but create was not
    mock_orm_operations['mock_structural_get_or_create'].assert_called_once()
    mock_orm_operations['mock_member_create'].assert_not_called()
    mock_orm_operations['mock_metadata_get_or_create'].assert_not_called()


@pytest.mark.django_db
def test_multiple_metadata_files(mock_metadata_file, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test handling of multiple metadata files"""
    # Create mock metadata files
    metadata_files = [
        mock_metadata_file(
            file_name="metadata1.xml",
            file_pid="hdl:11341/0000-0000-0000-3D7C",
            mime_type="application/xml",
            is_metadata_for="collection"
        ),
        mock_metadata_file(
            file_name="metadata2.xml",
            file_pid="hdl:11341/0000-0000-0000-3D7D",
            mime_type="text/plain",
            is_metadata_for="bundle",
            file_description="Additional metadata"
        )
    ]
    
    # Create structural info with multiple metadata files
    struct_info = mock_structural_info(metadata_files=metadata_files)
    
    # Import and verify
    result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify that get_or_create was called for each metadata file
    assert mock_orm_operations['mock_metadata_get_or_create'].call_count == len(metadata_files)


@pytest.mark.django_db
def test_multiple_collection_members(mock_collection_member, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test handling of multiple collection members"""
    # Create mock members
    members = [
        mock_collection_member(
            identifier="hdl:11341/0000-0000-0000-3D7E",
            identifier_type=CollectionHasCollectionMemberIdentifierType.HANDLE
        ),
        mock_collection_member(
            identifier="10.1234/test-doi",
            identifier_type=CollectionHasCollectionMemberIdentifierType.DOI
        )
    ]
    
    # Create structural info with multiple members
    struct_info = mock_structural_info(members=members)
    
    # Import and verify
    result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify that create was called for each member
    assert mock_orm_operations['mock_member_create'].call_count == len(members)


@pytest.mark.django_db
def test_metadata_file_updates(mock_metadata_file, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test that existing metadata files are properly updated when reimported"""
    # Create initial metadata file
    initial_file = mock_metadata_file(
        file_name="metadata1.xml",
        file_pid="hdl:11341/test-pid",
        mime_type="application/xml",
        is_metadata_for="collection"
    )
    
    # Create updated version with same PID but different attributes
    updated_file = mock_metadata_file(
        file_name="metadata1_updated.xml",
        file_pid="hdl:11341/test-pid",
        mime_type="text/xml",
        is_metadata_for="collection",
        file_description="Updated description"
    )
    
    # Set up mock to simulate existing file
    mock_orm_operations['mock_metadata_get_or_create'].return_value = (
        mock_orm_operations['metadata_file'],
        False  # Indicates file already existed
    )
    
    # First import
    struct_info = mock_structural_info(metadata_files=[initial_file])
    result1 = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Second import with updated data
    struct_info = mock_structural_info(metadata_files=[updated_file])
    result2 = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify update calls
    mock_file = mock_orm_operations['metadata_file']
    assert mock_file.file_name == "metadata1_updated.xml"
    assert mock_file.mime_type == "text/xml"
    assert mock_file.file_description == "Updated description"
    assert mock_file.save.called


@pytest.mark.django_db
def test_member_bundle_resolution(mock_collection_member, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test that bundle resolution is attempted for collection members"""
    # Create mock member
    member = mock_collection_member(
        identifier="hdl:11341/test-bundle",
        identifier_type=CollectionHasCollectionMemberIdentifierType.HANDLE
    )
    
    # Mock the resolve_bundle method
    mock_orm_operations['member'].resolve_bundle = MagicMock()
    
    # Create and import structural info
    struct_info = mock_structural_info(members=[member])
    result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify resolve_bundle was called
    mock_orm_operations['member'].resolve_bundle.assert_called_once()


@pytest.mark.django_db
def test_transaction_rollback(mock_collection_member, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test that transaction is rolled back when an error occurs"""
    # Create mock member that will cause an error
    member = mock_collection_member()
    
    # Make member creation raise an error
    mock_orm_operations['mock_member_create'].side_effect = Exception("Test error")
    
    # Create structural info
    struct_info = mock_structural_info(members=[member])
    
    # Attempt import and verify it raises the error
    with pytest.raises(Exception, match="Test error"):
        result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify that structural info was not saved
    mock_orm_operations['structural_info'].save.assert_not_called()


@pytest.mark.django_db
def test_optional_fields_handling(mock_metadata_file, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test handling of optional fields in metadata files"""
    # Test with and without optional fields
    files = [
        # With all fields
        mock_metadata_file(
            file_name="complete.xml",
            file_pid="hdl:11341/complete",
            file_description="Complete description"
        ),
        # Without optional fields
        mock_metadata_file(
            file_name="minimal.xml",
            file_pid="hdl:11341/minimal",
            file_description=None
        )
    ]
    
    # Create and import
    struct_info = mock_structural_info(metadata_files=files)
    result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify correct handling of optional fields
    calls = mock_orm_operations['mock_metadata_get_or_create'].call_args_list
    assert len(calls) == 2
    
    # Check complete file
    assert 'file_description' in calls[0].kwargs['defaults']
    
    # Check minimal file
    assert 'file_description' in calls[1].kwargs['defaults']
    assert calls[1].kwargs['defaults']['file_description'] is None


@pytest.mark.django_db
def test_identifier_type_mapping(mock_collection_member, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test correct mapping of identifier types from schema to model"""
    # Test both DOI and HANDLE types
    members = [
        mock_collection_member(
            identifier="10.1234/test-doi",
            identifier_type=CollectionHasCollectionMemberIdentifierType.DOI
        ),
        mock_collection_member(
            identifier="hdl:11341/test-handle",
            identifier_type=CollectionHasCollectionMemberIdentifierType.HANDLE
        )
    ]
    
    # Create and import
    struct_info = mock_structural_info(members=members)
    result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify correct identifier type mapping
    calls = mock_orm_operations['mock_member_create'].call_args_list
    assert calls[0].kwargs['identifier_type'] == "DOI"
    assert calls[1].kwargs['identifier_type'] == "HANDLE"


@pytest.mark.django_db
def test_member_order_preservation(mock_collection_member, mock_structural_info, mock_cmd_data, mock_collection, mock_orm_operations):
    """Test that member order is preserved when importing"""
    # Create members in specific order
    members = [
        mock_collection_member(identifier="hdl:11341/first"),
        mock_collection_member(identifier="hdl:11341/second"),
        mock_collection_member(identifier="hdl:11341/third")
    ]
    
    # Create and import
    struct_info = mock_structural_info(members=members)
    result = import_structural_info(mock_cmd_data(struct_info), mock_collection)
    
    # Verify order is preserved
    calls = mock_orm_operations['mock_member_create'].call_args_list
    assert calls[0].kwargs['order'] == 0
    assert calls[1].kwargs['order'] == 1
    assert calls[2].kwargs['order'] == 2 