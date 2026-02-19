import json
import wave
from unittest.mock import MagicMock, patch

import numpy as np

from lacos.storage.services.media_processing_service import (
    FFT_SAMPLES,
    MediaProcessingService,
)


def _make_samples(duration=0.5, sample_rate=44100, freq=440.0):
    """Create mono float32 samples of a sine wave."""
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _make_silence(duration=0.5, sample_rate=44100):
    n_samples = int(sample_rate * duration)
    return np.zeros(n_samples, dtype=np.float32)


def test_compute_spectrogram_produces_correct_shape():
    """Output should be [n_frames][n_bins] with values 0-255."""
    samples = _make_samples(duration=0.5)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    assert len(result) > 0
    n_bins = FFT_SAMPLES // 2 + 1
    assert len(result[0]) == n_bins

    for frame in result:
        for val in frame:
            assert 0 <= val <= 255


def test_compute_spectrogram_silence_is_dark():
    """Silence should produce mostly zero (dark) values."""
    samples = _make_silence(duration=0.5)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    flat = [v for frame in result for v in frame]
    avg = sum(flat) / len(flat)
    assert avg < 10, f"Silence should be dark but average intensity was {avg}"


def test_compute_spectrogram_tone_has_energy():
    """A pure sine wave should produce non-zero energy at its frequency bin."""
    samples = _make_samples(duration=0.5, freq=1000.0)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    expected_bin = int(1000.0 * FFT_SAMPLES / 44100)
    tone_values = [frame[expected_bin] for frame in result]
    max_val = max(tone_values)
    assert max_val > 100, f"1kHz tone should have strong energy but max was {max_val}"


def test_derivatives_current_checks_spectrogram_data():
    service = MediaProcessingService(bucket_service=MagicMock())

    with (
        patch.object(service, "_get_source_etag", return_value="etag-1"),
        patch.object(service, "_artifact_is_current", return_value=True),
        patch.object(service, "_spectrogram_data_is_current", return_value=False),
    ):
        assert service.derivatives_current("bucket", "audio.wav") is False


def test_spectrogram_data_key_suffix():
    service = MediaProcessingService(bucket_service=MagicMock())
    assert service._spectrogram_data_key("folder/audio.wav") == "folder/audio.wav.spectrogram.json"
