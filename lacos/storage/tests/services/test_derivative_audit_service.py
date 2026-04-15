"""Tests for DerivativeAuditService."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import EndpointConnectionError
from django.test import override_settings
from django.utils import timezone

from lacos.storage.models import DerivativeStatus
from lacos.storage.services.derivative_audit_service import DerivativeAuditService


def _make_s3_page(keys_with_etags):
    """Build a fake S3 list_objects_v2 page.

    keys_with_etags: list of (key, etag) tuples or just key strings.
    """
    contents = []
    for item in keys_with_etags:
        if isinstance(item, tuple):
            contents.append({"Key": item[0], "ETag": f'"{item[1]}"'})
        else:
            contents.append({"Key": item, "ETag": '"default-etag"'})
    return {"Contents": contents}


@pytest.mark.django_db
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_creates_status_rows(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([
            ("col/v1/content/audio1.wav", "etag1"),
            ("col/v1/content/audio2.wav", "etag2"),
            "col/v1/content/readme.txt",
        ]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator

    mock_service._artifact_exists.return_value = True
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)
    result = service.audit_bucket(bucket_name="lacos-production")

    assert result["success"] is True
    assert result["total_wav_files"] == 2
    assert result["with_peaks"] == 2
    assert result["missing_all_derivatives"] == 0
    assert DerivativeStatus.objects.count() == 2


@pytest.mark.django_db
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_no_wav_files(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page(["doc.xml", "image.png"]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator

    service = DerivativeAuditService(media_service=mock_service)
    result = service.audit_bucket(bucket_name="lacos-production")

    assert result["success"] is True
    assert result["total_wav_files"] == 0
    assert DerivativeStatus.objects.count() == 0


@patch("lacos.storage.services.derivative_audit_service.logger")
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
@override_settings(
    AWS_PRODUCTION_BUCKET_NAME="lacos-production",
    S3_PRODUCTION_BUCKET="grails-dev",
)
def test_audit_logs_resolved_bucket_and_endpoint(MockMPS, mock_logger):
    mock_service = MockMPS.return_value
    mock_service.bucket_service.production_bucket = "lacos-production"
    mock_service.bucket_service.endpoint_url = "https://rdsp.fds.uni-koeln.de"
    paginator = MagicMock()
    paginator.paginate.return_value = []
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator

    service = DerivativeAuditService(media_service=mock_service)
    service.audit_bucket(prefix="example/")

    mock_logger.info.assert_any_call(
        "Starting derivative audit",
        extra={
            "bucket_name": "lacos-production",
            "prefix": "example/",
            "bucket_service_production_bucket": "lacos-production",
            "endpoint_url": "https://rdsp.fds.uni-koeln.de",
            "aws_production_bucket_name": "lacos-production",
            "legacy_production_bucket": "grails-dev",
        },
    )


@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
@override_settings(
    AWS_PRODUCTION_BUCKET_NAME="lacos-production",
    S3_PRODUCTION_BUCKET="grails-dev",
)
def test_audit_defaults_to_bucket_service_production_bucket(MockMPS):
    mock_service = MockMPS.return_value
    mock_service.bucket_service.production_bucket = "lacos-production"
    paginator = MagicMock()
    paginator.paginate.return_value = []
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator

    service = DerivativeAuditService(media_service=mock_service)
    result = service.audit_bucket()

    assert result["bucket_name"] == "lacos-production"
    paginator.paginate.assert_called_once_with(Bucket="lacos-production")


@pytest.mark.django_db
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_partial_derivatives(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([("audio.wav", "etag1")]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator

    # peaks exists, spectrogram+pitch missing
    def artifact_exists(bucket, key):
        return key.endswith(".peaks.json")

    mock_service._artifact_exists.side_effect = artifact_exists
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)
    result = service.audit_bucket(bucket_name="lacos-production")

    assert result["with_peaks"] == 1
    assert result["with_spectrogram"] == 0
    assert result["with_pitch"] == 0
    assert result["missing_all_derivatives"] == 0

    ds = DerivativeStatus.objects.get()
    assert ds.peaks_exists is True
    assert ds.spectrogram_exists is False
    assert ds.pitch_exists is False


@pytest.mark.django_db
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_updates_existing_row(MockMPS):
    """Running audit twice should update, not duplicate."""
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([("audio.wav", "etag1")]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator
    mock_service._artifact_exists.return_value = False
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)

    # First audit: no derivatives
    service.audit_bucket(bucket_name="lacos-production")
    assert DerivativeStatus.objects.count() == 1
    assert DerivativeStatus.objects.get().peaks_exists is False

    # Second audit: derivatives now exist
    mock_service._artifact_exists.return_value = True
    service.audit_bucket(bucket_name="lacos-production")
    assert DerivativeStatus.objects.count() == 1
    assert DerivativeStatus.objects.get().peaks_exists is True


@pytest.mark.django_db
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_error_is_counted(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([("audio.wav", "etag1")]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator
    mock_service._artifact_exists.side_effect = Exception("S3 timeout")
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)
    result = service.audit_bucket(bucket_name="lacos-production")

    assert result["success"] is False
    assert result["errors"] == 1
    assert DerivativeStatus.objects.count() == 0


@pytest.mark.django_db
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_counts_existing_derivatives_even_when_not_current(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([("audio.wav", "fresh-etag")]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator

    def artifact_exists(bucket, key):
        return key.endswith(".pitch.bin")

    mock_service._artifact_exists.side_effect = artifact_exists
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)
    result = service.audit_bucket(bucket_name="lacos-production")

    assert result["with_peaks"] == 0
    assert result["with_spectrogram"] == 0
    assert result["with_pitch"] == 1

    ds = DerivativeStatus.objects.get()
    assert ds.peaks_exists is False
    assert ds.spectrogram_exists is False
    assert ds.pitch_exists is True


@pytest.mark.django_db
@override_settings(
    DERIVATIVE_AUDIT_ARTIFACT_DELAY_SECONDS=0.4,
    DERIVATIVE_AUDIT_FILE_DELAY_SECONDS=0.25,
    DERIVATIVE_AUDIT_PAGE_DELAY_SECONDS=2.5,
)
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_uses_configured_throttle_delays(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page([("audio.wav", "etag1")]),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator
    mock_service._artifact_exists.return_value = True
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)

    with patch("lacos.storage.services.derivative_audit_service.time.sleep") as mock_sleep:
        result = service.audit_bucket(bucket_name="lacos-production")

    assert result["success"] is True
    assert service.artifact_delay == 0.4
    assert service.throttle_delay == 0.25
    assert service.throttle_page_delay == 2.5
    assert mock_sleep.call_args_list == [
        ((0.4,), {}),
        ((0.4,), {}),
        ((0.25,), {}),
        ((2.5,), {}),
    ]


@override_settings(
    DERIVATIVE_AUDIT_ARTIFACT_DELAY_SECONDS=-1,
    DERIVATIVE_AUDIT_FILE_DELAY_SECONDS="invalid",
    DERIVATIVE_AUDIT_PAGE_DELAY_SECONDS=-3,
    DERIVATIVE_AUDIT_CONNECTIVITY_BACKOFF_BASE_SECONDS="invalid",
    DERIVATIVE_AUDIT_CONNECTIVITY_BACKOFF_MAX_SECONDS=-2,
    DERIVATIVE_AUDIT_MAX_CONSECUTIVE_CONNECTIVITY_FAILURES=0,
)
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_throttle_settings_fall_back_or_clamp(MockMPS):
    service = DerivativeAuditService(media_service=MockMPS.return_value)

    assert service.artifact_delay == 0.0
    assert service.throttle_delay == service.DEFAULT_THROTTLE_DELAY
    assert service.throttle_page_delay == 0.0
    assert service.connectivity_backoff_base == service.DEFAULT_CONNECTIVITY_BACKOFF_BASE
    assert service.connectivity_backoff_max == 0.0
    assert (
        service.max_consecutive_connectivity_failures == 1
    )


@pytest.mark.django_db
@override_settings(
    DERIVATIVE_AUDIT_ARTIFACT_DELAY_SECONDS=0,
    DERIVATIVE_AUDIT_FILE_DELAY_SECONDS=0,
    DERIVATIVE_AUDIT_PAGE_DELAY_SECONDS=0,
    DERIVATIVE_AUDIT_CONNECTIVITY_BACKOFF_BASE_SECONDS=1.5,
    DERIVATIVE_AUDIT_CONNECTIVITY_BACKOFF_MAX_SECONDS=5.0,
    DERIVATIVE_AUDIT_MAX_CONSECUTIVE_CONNECTIVITY_FAILURES=2,
)
@patch("lacos.storage.services.derivative_audit_service.MediaProcessingService")
def test_audit_aborts_after_repeated_connectivity_failures(MockMPS):
    mock_service = MockMPS.return_value
    paginator = MagicMock()
    paginator.paginate.return_value = [
        _make_s3_page(
            [
                ("audio1.wav", "etag1"),
                ("audio2.wav", "etag2"),
                ("audio3.wav", "etag3"),
            ]
        ),
    ]
    mock_service.bucket_service.s3_client.get_paginator.return_value = paginator
    mock_service._artifact_exists.side_effect = EndpointConnectionError(
        endpoint_url="https://s3.example.test"
    )
    mock_service._peaks_key.side_effect = lambda k: f"{k}.peaks.json"
    mock_service._spectrogram_data_key.side_effect = lambda k: f"{k}.spectrogram.bin"
    mock_service._pitch_key.side_effect = lambda k: f"{k}.pitch.bin"

    service = DerivativeAuditService(media_service=mock_service)

    with patch("lacos.storage.services.derivative_audit_service.time.sleep") as mock_sleep:
        result = service.audit_bucket(bucket_name="lacos-production")

    assert result["success"] is False
    assert result["aborted"] is True
    assert result["errors"] == 2
    assert result["total_wav_files"] == 2
    assert "connectivity failures" in result["error"].lower()
    assert DerivativeStatus.objects.count() == 0
    assert mock_sleep.call_args_list == [
        ((1.5,), {}),
        ((3.0,), {}),
    ]
