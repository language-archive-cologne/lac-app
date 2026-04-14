"""Tests that generate_peaks_task populates DerivativeStatus on success."""

import pytest
from unittest.mock import patch

from lacos.storage.media_tasks import generate_peaks_task
from lacos.storage.models import DerivativeStatus


@pytest.mark.django_db
@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_successful_generation_creates_derivative_status(MockService):
    mock_service = MockService.return_value
    mock_service.generate_peaks.return_value = {
        "success": True,
        "peaks_key": "col/v1/derivatives/audio.wav.peaks.json",
        "spectrogram_data_key": "col/v1/derivatives/audio.wav.spectrogram.bin",
        "pitch_key": "col/v1/derivatives/audio.wav.pitch.bin",
    }

    result = generate_peaks_task.call_local("lacos-production", "col/v1/content/audio.wav")

    assert result["success"] is True
    assert DerivativeStatus.objects.count() == 1
    ds = DerivativeStatus.objects.get()
    assert ds.bucket_name == "lacos-production"
    assert ds.source_s3_key == "col/v1/content/audio.wav"
    assert ds.peaks_exists is True
    assert ds.spectrogram_exists is True
    assert ds.pitch_exists is True


@pytest.mark.django_db
@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_failed_generation_does_not_create_status(MockService):
    mock_service = MockService.return_value
    mock_service.generate_peaks.return_value = {
        "success": False,
        "error": "Source file not found",
    }

    result = generate_peaks_task.call_local("lacos-production", "missing.wav")

    assert result["success"] is False
    assert DerivativeStatus.objects.count() == 0


@pytest.mark.django_db
@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_partial_generation_reflects_in_status(MockService):
    """When pitch_key is missing from result, pitch_exists should be False."""
    mock_service = MockService.return_value
    mock_service.generate_peaks.return_value = {
        "success": True,
        "peaks_key": "audio.wav.peaks.json",
        "spectrogram_data_key": "audio.wav.spectrogram.bin",
        # no pitch_key
    }

    generate_peaks_task.call_local("bucket", "audio.wav")

    ds = DerivativeStatus.objects.get()
    assert ds.peaks_exists is True
    assert ds.spectrogram_exists is True
    assert ds.pitch_exists is False


@pytest.mark.django_db
@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_skipped_generation_preserves_full_derivative_status(MockService):
    mock_service = MockService.return_value
    mock_service.generate_peaks.return_value = {
        "success": True,
        "source_etag": "etag-123",
        "peaks_key": "audio.wav.peaks.json",
        "spectrogram_data_key": "audio.wav.spectrogram.bin",
        "pitch_key": "audio.wav.pitch.bin",
        "skipped": True,
    }

    result = generate_peaks_task.call_local("bucket", "audio.wav")

    assert result["success"] is True
    ds = DerivativeStatus.objects.get()
    assert ds.source_etag == "etag-123"
    assert ds.peaks_exists is True
    assert ds.spectrogram_exists is True
    assert ds.pitch_exists is True
