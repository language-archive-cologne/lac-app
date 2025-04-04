import pytest
import os
from unittest.mock import patch

# Models and Schemas
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd
from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.models.datatype import XmlDate

# Function to test
from lacos.blam.mappers.bundle.read.import_bundle_header import import_bundle_header


# --- Fixtures ---

@pytest.fixture
def test_bundle():
    """Create a test bundle for testing."""
    return Bundle.objects.create(identifier="test-header-bundle")

@pytest.fixture
def real_bundle_xml():
    """Loads the content of a real bundle XML file."""
    # Adjust path as needed relative to the test execution directory or use absolute paths
    # Assuming tests run from the project root where 'data' directory exists
    xml_path = os.path.join('data', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        # Fallback path if the first one doesn't exist (adjust if needed)
        xml_path = os.path.join('lacos', 'data', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
        try:
             with open(xml_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
             pytest.fail(f"Test bundle XML file not found at expected paths: {xml_path}")


@pytest.fixture
def real_cmd_data(real_bundle_xml):
    """Parses the real bundle XML into a Cmd object."""
    parser = XmlParser()
    try:
        return parser.from_string(real_bundle_xml, Cmd)
    except Exception as e:
        pytest.fail(f"Failed to parse real_bundle_xml: {e}")

# --- Test Cases ---

@pytest.mark.django_db
def test_import_bundle_header_creates_object(real_cmd_data, test_bundle):
    """Verify that a BundleHeader object is created in the database."""
    header = import_bundle_header(real_cmd_data, test_bundle)

    assert header is not None
    assert isinstance(header, BundleHeader)
    assert header.id is not None  # Check if it has been saved to DB
    assert BundleHeader.objects.count() == 1
    # Verify the association with the bundle
    assert test_bundle.header.count() == 1
    assert test_bundle.header.first() == header


@pytest.mark.django_db
def test_import_bundle_header_maps_data_correctly(real_cmd_data, test_bundle):
    """Verify that data from the XML header is mapped correctly to model fields."""
    header = import_bundle_header(real_cmd_data, test_bundle)
    xml_header = real_cmd_data.header

    assert header is not None
    assert header.md_self_link == xml_header.md_self_link.value
    # Assuming the first creator is used
    assert header.md_creator == xml_header.md_creator[0].value 
    assert header.md_creation_date == xml_header.md_creation_date.value.to_date() # Compare date part
    assert header.md_profile == xml_header.md_profile.value


@pytest.mark.django_db
def test_import_bundle_header_handles_missing_header(test_bundle):
    """Verify behavior when the Cmd object has no header."""
    # Create a minimal Cmd object without a header
    cmd_data = Cmd()
    cmd_data.header = None # Explicitly set to None

    header = import_bundle_header(cmd_data, test_bundle)
    assert header is None
    assert BundleHeader.objects.count() == 0
    assert test_bundle.header.count() == 0


@pytest.mark.django_db
def test_import_bundle_header_handles_missing_self_link(real_cmd_data, test_bundle):
    """Verify behavior when MdSelfLink is missing in the header."""
    real_cmd_data.header.md_self_link = None # Simulate missing self link

    header = import_bundle_header(real_cmd_data, test_bundle)
    assert header is None
    assert BundleHeader.objects.count() == 0
    assert test_bundle.header.count() == 0


@pytest.mark.django_db
def test_import_bundle_header_updates_existing(real_cmd_data, test_bundle):
    """Verify that calling the function again updates the existing header based on md_self_link."""
    # 1. Import for the first time
    header1 = import_bundle_header(real_cmd_data, test_bundle)
    assert header1 is not None
    assert header1.md_creator == "Language Archive Cologne"
    assert BundleHeader.objects.count() == 1
    assert test_bundle.header.count() == 1

    # 2. Modify the data in the Cmd object (simulate an updated XML)
    new_creator = "Updated Creator Name"
    real_cmd_data.header.md_creator[0].value = new_creator
    # Ensure date is different but valid for comparison
    new_date_str = "2024-01-01"
    real_cmd_data.header.md_creation_date.value = XmlDate.from_string(new_date_str)

    # 3. Import again
    header2 = import_bundle_header(real_cmd_data, test_bundle)
    assert header2 is not None
    assert BundleHeader.objects.count() == 1 # Should still be only one record
    assert test_bundle.header.count() == 1 # Still only one header in the bundle

    # 4. Verify it's the same object and it has been updated
    assert header1.id == header2.id
    assert header2.md_creator == new_creator
    assert header2.md_creation_date == XmlDate.from_string(new_date_str).to_date()
