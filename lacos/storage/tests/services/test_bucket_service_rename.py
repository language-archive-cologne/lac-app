import pytest
from unittest.mock import MagicMock
from botocore.exceptions import ClientError

from lacos.storage.services.bucket_service import BucketService


def _build_service(accessible_buckets=None):
    """Create a BucketService instance without running __init__."""
    service = object.__new__(BucketService)
    service.workspace_buckets = accessible_buckets[:] if accessible_buckets else []
    service.s3_client = MagicMock()
    service.ensure_bucket_exists = MagicMock(return_value=True)
    service.get_all_accessible_buckets = MagicMock(return_value=accessible_buckets or [])
    return service


def _client_error(code):
    return ClientError({'Error': {'Code': code}}, 'Operation')


def test_rename_folder_success():
    service = _build_service(['test-bucket'])

    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [
            {"Key": "collections/old-folder/file1.txt"},
            {"Key": "collections/old-folder/sub/file2.txt"},
        ]}
    ]
    service.s3_client.get_paginator.return_value = paginator
    service.s3_client.list_objects_v2.return_value = {"KeyCount": 0}

    result = service.rename_folder("test-bucket", "collections/old-folder/", "renamed")

    assert result["success"] is True
    copy_calls = service.s3_client.copy_object.call_args_list
    assert len(copy_calls) == 2
    assert copy_calls[0].kwargs["Key"] == "collections/renamed/file1.txt"
    assert copy_calls[1].kwargs["Key"] == "collections/renamed/sub/file2.txt"
    assert service.s3_client.delete_object.call_count == 2


def test_rename_folder_conflict():
    service = _build_service(['bucket'])
    service.s3_client.list_objects_v2.return_value = {"KeyCount": 1}

    result = service.rename_folder("bucket", "folder/", "existing")

    assert result["success"] is False
    assert "already exists" in result["error"].lower()


def test_rename_file_success():
    service = _build_service(['bucket'])
    service.s3_client.head_object.side_effect = _client_error('404')

    result = service.rename_file("bucket", "folder/file.txt", "renamed.txt")

    assert result["success"] is True
    service.s3_client.copy_object.assert_called_once_with(
        Bucket="bucket",
        CopySource={"Bucket": "bucket", "Key": "folder/file.txt"},
        Key="folder/renamed.txt",
    )
    service.s3_client.delete_object.assert_called_once_with(Bucket="bucket", Key="folder/file.txt")


def test_rename_file_conflict():
    service = _build_service(['bucket'])
    service.s3_client.head_object.return_value = {}

    result = service.rename_file("bucket", "folder/file.txt", "existing.txt")

    assert result["success"] is False


def test_rename_bucket_success():
    service = _build_service(['old-bucket'])

    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "file1"}, {"Key": "path/file2"}]}
    ]
    service.s3_client.get_paginator.return_value = paginator

    result = service.rename_bucket("old-bucket", "new-bucket")

    assert result["success"] is True
    service.ensure_bucket_exists.assert_called_once_with("new-bucket")
    assert service.s3_client.copy_object.call_count == 2
    service.s3_client.delete_bucket.assert_called_once_with(Bucket="old-bucket")
    assert service.workspace_buckets == ["new-bucket"]


def test_rename_bucket_conflict():
    service = _build_service(['old', 'existing'])
    result = service.rename_bucket("old", "existing")
    assert result["success"] is False
