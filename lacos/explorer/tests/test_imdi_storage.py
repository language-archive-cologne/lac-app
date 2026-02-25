from unittest.mock import MagicMock

from lacos.explorer.services.imdi_storage import ImdiStorageService


def _mock_s3_client() -> MagicMock:
    return MagicMock()


def test_discover_imdi_files_returns_keys():
    s3 = _mock_s3_client()
    paginator = MagicMock()
    s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "archive/corpus.imdi"},
                {"Key": "archive/session1.imdi"},
                {"Key": "archive/readme.txt"},
                {"Key": "archive/session2.imdi"},
            ],
        },
    ]

    service = ImdiStorageService(s3_client=s3)
    keys = service.discover_imdi_files("test-bucket", "archive/")

    assert keys == [
        "archive/corpus.imdi",
        "archive/session1.imdi",
        "archive/session2.imdi",
    ]
    s3.get_paginator.assert_called_once_with("list_objects_v2")


def test_discover_imdi_files_empty_bucket():
    s3 = _mock_s3_client()
    paginator = MagicMock()
    s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [{"Contents": []}]

    service = ImdiStorageService(s3_client=s3)
    keys = service.discover_imdi_files("test-bucket", "archive/")

    assert keys == []


def test_discover_imdi_files_no_contents_key():
    s3 = _mock_s3_client()
    paginator = MagicMock()
    s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [{}]

    service = ImdiStorageService(s3_client=s3)
    keys = service.discover_imdi_files("test-bucket", "archive/")

    assert keys == []


def test_read_imdi_file_returns_bytes():
    s3 = _mock_s3_client()
    body = MagicMock()
    body.read.return_value = b"<METATRANSCRIPT/>"
    s3.get_object.return_value = {"Body": body}

    service = ImdiStorageService(s3_client=s3)
    data = service.read_imdi_file("test-bucket", "archive/corpus.imdi")

    assert data == b"<METATRANSCRIPT/>"
    s3.get_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="archive/corpus.imdi",
    )


def test_read_imdi_file_returns_none_on_error():
    s3 = _mock_s3_client()
    s3.get_object.side_effect = RuntimeError("not found")

    service = ImdiStorageService(s3_client=s3)
    data = service.read_imdi_file("test-bucket", "missing.imdi")

    assert data is None


def test_find_root_imdi_prefers_shallowest():
    s3 = _mock_s3_client()
    service = ImdiStorageService(s3_client=s3)

    keys = [
        "archive/sub/deep/session.imdi",
        "archive/corpus.imdi",
        "archive/sub/other.imdi",
    ]
    root = service.find_root_imdi(keys, "archive/")

    assert root == "archive/corpus.imdi"


def test_find_root_imdi_empty_list():
    s3 = _mock_s3_client()
    service = ImdiStorageService(s3_client=s3)

    assert service.find_root_imdi([], "archive/") is None
