"""Tests for media processing tasks (scan_and_generate_peaks_task)."""

from unittest.mock import MagicMock, patch, call

from lacos.storage.media_tasks import scan_and_generate_peaks_task


def _make_s3_page(keys):
    """Build a fake S3 list_objects_v2 page."""
    return {"Contents": [{"Key": k} for k in keys]}


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_enqueues_audio_files(MockBucketService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([
            "folder/track1.wav",
            "folder/track2.mp3",
            "folder/image.png",
            "folder/doc.xml",
        ]),
    ]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    result = scan_and_generate_peaks_task.call_local(
        bucket_name="test-bucket", folder_path="folder"
    )

    assert result["success"] is True
    assert result["enqueued"] == 2
    assert result["audio_files"] == 2
    mock_gen_task.assert_any_call("test-bucket", "folder/track1.wav")
    mock_gen_task.assert_any_call("test-bucket", "folder/track2.mp3")


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_skips_peaks_json_files(MockBucketService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([
            "folder/track.wav",
            "folder/track.wav.peaks.json",
            "folder/track.wav.spectrogram.json",
        ]),
    ]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    result = scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path="folder"
    )

    assert result["enqueued"] == 1
    mock_gen_task.assert_called_once_with("b", "folder/track.wav")


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_no_audio_files(MockBucketService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page(["folder/readme.txt", "folder/photo.jpg"]),
    ]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    result = scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path="folder"
    )

    assert result["success"] is True
    assert result["enqueued"] == 0
    mock_gen_task.assert_not_called()


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_empty_contents(MockBucketService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    result = scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path=""
    )

    assert result["success"] is True
    assert result["enqueued"] == 0


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.media_tasks.BackgroundTaskService")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_tracking_marks_success(MockBucketService, MockBGService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page(["a.flac", "b.ogg"]),
    ]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    result = scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path="", tracking_id="track-123"
    )

    assert result["success"] is True
    MockBGService.mark_running.assert_called_once_with("track-123", message="Scanning for audio files")
    MockBGService.mark_success.assert_called_once()


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.media_tasks.BackgroundTaskService")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_tracking_marks_failure_on_error(MockBucketService, MockBGService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.side_effect = Exception("S3 connection refused")
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    result = scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path="", tracking_id="track-456"
    )

    assert result["success"] is False
    MockBGService.mark_failed.assert_called_once()


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_prefix_gets_trailing_slash(MockBucketService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path="audio/recordings"
    )

    paginator.paginate.assert_called_once_with(
        Bucket="b", Prefix="audio/recordings/"
    )


@patch("lacos.storage.media_tasks.generate_peaks_task")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_no_prefix_when_folder_path_empty(MockBucketService, mock_gen_task):
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    MockBucketService.return_value.s3_client.get_paginator.return_value = paginator

    scan_and_generate_peaks_task.call_local(
        bucket_name="b", folder_path=""
    )

    paginator.paginate.assert_called_once_with(Bucket="b")
