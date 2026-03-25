from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lacos.storage.services.file_discovery_service import FileDiscoveryService


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset FileDiscoveryService singleton between tests."""
    FileDiscoveryService._instance = None
    yield
    FileDiscoveryService._instance = None


@pytest.fixture
def service():
    svc = FileDiscoveryService(skip_bucket_check=True)
    svc.s3_client = MagicMock()
    return svc


def test_head_s3_object_returns_etag(service):
    """Happy path: returns parsed metadata from HEAD response."""
    service.s3_client.head_object.return_value = {
        "ETag": '"abc123"',
        "ContentLength": 1024,
        "LastModified": "2026-01-01T00:00:00Z",
    }

    result = service.head_s3_object("my-bucket", "path/to/file.xml")

    assert result["ETag"] == "abc123"
    assert result["ContentLength"] == 1024
    service.s3_client.head_object.assert_called_once_with(
        Bucket="my-bucket", Key="path/to/file.xml"
    )


def test_head_s3_object_returns_none_for_missing_key(service):
    """Edge case: returns None when the object doesn't exist."""
    error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
    service.s3_client.head_object.side_effect = ClientError(
        error_response, "HeadObject"
    )

    result = service.head_s3_object("my-bucket", "missing/key.xml")

    assert result is None


def test_head_s3_object_raises_on_other_errors(service):
    """Error path: re-raises non-404 ClientErrors."""
    error_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
    service.s3_client.head_object.side_effect = ClientError(
        error_response, "HeadObject"
    )

    with pytest.raises(ClientError):
        service.head_s3_object("my-bucket", "forbidden/key.xml")
