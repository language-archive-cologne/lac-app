import os
import pytest
from unittest.mock import patch, MagicMock

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd


def get_bundle_xml_from_file():
    """Get the XML content from a real bundle file in the data directory."""
    xml_path = os.path.join('data', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        xml_path = os.path.join('data', 'zaghawa', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()


def test_read_real_bundle_xml():
    """Test reading a real bundle XML file using BundleImporter."""
    xml_content = get_bundle_xml_from_file()
    
    cmd_data = BundleImporter.validate_xml(xml_content)
    assert isinstance(cmd_data, Cmd)
    
    repository = cmd_data.components.blam_bundle_repository_v1_0
    
    general_info = repository.bundle_general_info
    title = general_info.bundle_display_title
    assert title is not None
    print(f"\nBundle title: {title}")
    
    pub_info = repository.bundle_publication_info
    pub_year = pub_info.bundle_publication_year
    assert pub_year is not None
    print(f"Publication year: {pub_year}")
    
    admin_info = repository.bundle_administrative_info
    access = admin_info.access
    assert access is not None
    print(f"Access: {access.value}")
    
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_cmd_to_models') as mock_import:
        mock_bundle = MagicMock()
        mock_bundle.general_info.display_title = title
        mock_import.return_value = mock_bundle
        
