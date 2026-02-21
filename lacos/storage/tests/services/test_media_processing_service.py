import errno
import struct
from unittest.mock import MagicMock, patch

import numpy as np

from lacos.storage.services.media_processing_service import (
    FFT_SAMPLES,
    HOP_DIVISOR,
    N_MELS,
    TARGET_SAMPLE_RATE,
    MediaProcessingService,
    _hz_to_mel,
)


def _make_samples(duration=0.5, sample_rate=44100, freq=440.0):
    """Create mono float32 samples of a sine wave."""
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _make_silence(duration=0.5, sample_rate=44100):
    n_samples = int(sample_rate * duration)
    return np.zeros(n_samples, dtype=np.float32)


def _parse_spectrogram_binary(data):
    """Parse binary spectrogram payload into (n_frames, n_bins, uint8_array)."""
    assert len(data) >= 6, "Binary payload must be at least 6 bytes"
    n_frames, n_bins = struct.unpack_from("<IH", data)
    body = data[6:]
    assert len(body) == n_frames * n_bins
    arr = np.frombuffer(body, dtype=np.uint8).reshape(n_frames, n_bins)
    return n_frames, n_bins, arr


def test_compute_spectrogram_produces_correct_shape():
    """Output should be binary with [n_frames][n_bins] uint8 values 0-255."""
    samples = _make_samples(duration=0.5)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    assert isinstance(result, bytes)
    n_frames, n_bins, arr = _parse_spectrogram_binary(result)

    assert n_frames > 0
    assert n_bins == N_MELS
    assert arr.min() >= 0
    assert arr.max() <= 255


def test_compute_spectrogram_silence_is_uniform():
    """Silence should produce uniform values (near-zero variance)."""
    samples = _make_silence(duration=0.5)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    assert isinstance(result, bytes)
    _n_frames, _n_bins, arr = _parse_spectrogram_binary(result)

    std = float(np.std(arr.astype(np.float64)))
    assert std < 1.0, f"Silence should be uniform but std was {std}"


def test_compute_spectrogram_tone_has_energy():
    """A pure sine wave should produce non-zero energy at its frequency bin."""
    samples = _make_samples(duration=0.5, freq=1000.0)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    assert isinstance(result, bytes)
    _n_frames, _n_bins, arr = _parse_spectrogram_binary(result)

    # Compute expected mel bin for 1 kHz tone
    mel_max = _hz_to_mel(TARGET_SAMPLE_RATE / 2.0)
    expected_mel_bin = int(N_MELS * _hz_to_mel(1000.0) / mel_max)
    tone_values = arr[:, expected_mel_bin]
    max_val = int(tone_values.max())
    assert max_val > 100, f"1kHz tone should have strong energy but max was {max_val}"


def test_compute_spectrogram_short_audio_returns_empty():
    """Audio shorter than FFT window should return empty bytes."""
    samples = np.zeros(100, dtype=np.float32)

    service = MediaProcessingService(bucket_service=MagicMock())
    with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
        result = service._compute_spectrogram("dummy.wav")

    assert result == b""


def test_compute_spectrogram_uniform_resolution():
    """Short and long files should produce the same frames-per-second."""
    service = MediaProcessingService(bucket_service=MagicMock())
    hop = max(64, FFT_SAMPLES // HOP_DIVISOR)

    for duration in (0.5, 5.0, 30.0):
        samples = _make_samples(duration=duration)
        with patch.object(service, "_decode_audio_to_pcm", return_value=samples):
            result = service._compute_spectrogram("dummy.wav")
        n_frames, _, _ = _parse_spectrogram_binary(result)
        expected = (len(samples) - FFT_SAMPLES) // hop + 1
        assert n_frames == expected, (
            f"duration={duration}s: got {n_frames} frames, expected {expected}"
        )


def test_derivatives_current_uses_artifact_is_current_for_both():
    service = MediaProcessingService(bucket_service=MagicMock())

    calls = []

    def tracking_artifact_is_current(bucket, key, etag):
        calls.append(key)
        # peaks current, spectrogram not
        return key.endswith(".peaks.json")

    with (
        patch.object(service, "_get_source_etag", return_value="etag-1"),
        patch.object(service, "_artifact_is_current", side_effect=tracking_artifact_is_current),
    ):
        assert service.derivatives_current("bucket", "audio.wav") is False

    assert len(calls) == 2
    assert any(k.endswith(".peaks.json") for k in calls)
    assert any(k.endswith(".spectrogram.bin") for k in calls)


def test_spectrogram_data_key_suffix():
    service = MediaProcessingService(bucket_service=MagicMock())
    assert service._spectrogram_data_key("folder/audio.wav") == "folder/audio.wav.spectrogram.bin"


def test_generate_peaks_returns_clean_error_when_tmp_dir_has_no_space():
    service = MediaProcessingService(bucket_service=MagicMock())
    with (
        patch.object(service, "_get_source_etag", return_value="etag-1"),
        patch.object(service, "_artifact_is_current", return_value=False),
        patch("lacos.storage.services.media_processing_service.tempfile.TemporaryDirectory") as mock_tmp,
    ):
        mock_tmp.side_effect = OSError(errno.ENOSPC, "No space left on device")
        result = service.generate_peaks("bucket", "folder/audio.wav")

    assert result["success"] is False
    assert result["error_code"] == "no_space"
    assert "No space left on device" in result["error"]


def test_generate_peaks_preflight_stops_when_tmp_space_is_too_low():
    bucket_service = MagicMock()
    service = MediaProcessingService(bucket_service=bucket_service)

    with (
        patch.object(service, "_get_source_etag", return_value="etag-1"),
        patch.object(service, "_get_source_size", return_value=1024 * 1024 * 1024),
        patch.object(service, "_artifact_is_current", return_value=False),
        patch.object(service, "_tmp_free_bytes", return_value=50 * 1024 * 1024),
    ):
        result = service.generate_peaks("bucket", "folder/audio.wav")

    assert result["success"] is False
    assert result["error_code"] == "no_space"
    bucket_service.s3_client.download_file.assert_not_called()
