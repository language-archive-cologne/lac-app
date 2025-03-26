import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd


def get_collection_xml_from_file():
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


def test_read_real_collection_xml():
    """Test reading a real collection XML file using CollectionImporter."""
    xml_content = get_collection_xml_from_file()
    
    cmd_data = CollectionImporter.validate_xml(xml_content)
    assert isinstance(cmd_data, Cmd)
    
    repository = cmd_data.components.blam_collection_repository_v1_0
    
    general_info = repository.collection_general_info
    title = general_info.collection_display_title
    assert title is not None
    print(f"\nCollection title: {title}")
    
    pub_info = repository.collection_publication_info
    pub_year = pub_info.collection_publication_year
    assert pub_year is not None
    print(f"Publication year: {pub_year}")
    
    admin_info = repository.collection_administrative_info
    access = admin_info.access.value
    assert access is not None
    print(f"Access: {access}")
    
    with patch('lacos.blam.mappers.collection.read.collection_importer.CollectionImporter._import_cmd_to_models') as mock_import:
        mock_collection = MagicMock()
        mock_collection.general_info.display_title = title
        mock_import.return_value = mock_collection
        
        print("\nTo import collection XML into Django models (saves to database):")
        print("collection = CollectionImporter.import_from_xml(xml_content)")
        