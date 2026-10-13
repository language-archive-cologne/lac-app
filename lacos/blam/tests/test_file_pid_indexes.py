"""Resource lookups by handle PID must use an index (issue #209)."""

import pytest

from lacos.blam.models.base_structural_info import AdditionalMetadataFile
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.bundle.bundle_structural_info import OtherResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource


@pytest.mark.parametrize(
    "model",
    [MediaResource, WrittenResource, OtherResource, AdditionalMetadataFile],
)
def test_file_pid_is_indexed(model):
    assert model._meta.get_field("file_pid").db_index
