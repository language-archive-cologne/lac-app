"""Tests for YIN F0 pitch extraction algorithm."""

import numpy as np

from lacos.storage.services.pitch import F0_CEIL, F0_FLOOR, compute_f0


def _make_sine(freq, duration, sr=44100):
    """Generate a float32 sine wave at the given frequency."""
    n_samples = int(sr * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def test_returns_float32_array():
    """compute_f0 must return a float32 numpy array."""
    samples = _make_sine(200.0, 0.5)
    result = compute_f0(samples, 44100)
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32


def test_pure_tone_detected():
    """A 200 Hz sine wave should be detected with median ~200 Hz."""
    samples = _make_sine(200.0, 1.0)
    f0 = compute_f0(samples, 44100)
    voiced = f0[f0 > 0]
    assert len(voiced) > 0, "Should detect voiced frames"
    median_f0 = float(np.median(voiced))
    assert abs(median_f0 - 200.0) < 10.0, f"Expected ~200 Hz, got {median_f0:.1f} Hz"


def test_silence_is_unvoiced():
    """All-zero input should produce all-unvoiced (0.0) frames."""
    samples = np.zeros(44100, dtype=np.float32)
    f0 = compute_f0(samples, 44100)
    assert np.all(f0 == 0.0), "Silence should be entirely unvoiced"


def test_low_tone_detected():
    """A 100 Hz tone (near floor) should be correctly detected."""
    samples = _make_sine(100.0, 1.0)
    f0 = compute_f0(samples, 44100)
    voiced = f0[f0 > 0]
    assert len(voiced) > 0, "Should detect voiced frames for 100 Hz"
    median_f0 = float(np.median(voiced))
    assert abs(median_f0 - 100.0) < 10.0, f"Expected ~100 Hz, got {median_f0:.1f} Hz"


def test_high_tone_detected():
    """A 400 Hz tone (near ceil) should be correctly detected."""
    samples = _make_sine(400.0, 1.0)
    f0 = compute_f0(samples, 44100)
    voiced = f0[f0 > 0]
    assert len(voiced) > 0, "Should detect voiced frames for 400 Hz"
    median_f0 = float(np.median(voiced))
    assert abs(median_f0 - 400.0) < 15.0, f"Expected ~400 Hz, got {median_f0:.1f} Hz"


def test_tone_outside_range_is_unvoiced():
    """A 200 Hz tone analyzed with floor=300, ceil=450 should be unvoiced.

    YIN detects subharmonics of high-frequency tones, so testing with a tone
    above ceil is unreliable.  Instead we verify that a known-frequency tone
    is rejected when the allowed range excludes it entirely.
    """
    samples = _make_sine(200.0, 1.0)
    f0 = compute_f0(samples, 44100, f0_floor=300.0, f0_ceil=450.0)
    voiced_ratio = np.count_nonzero(f0) / max(len(f0), 1)
    assert voiced_ratio < 0.2, (
        f"200 Hz tone with floor=300 should be mostly unvoiced "
        f"but {voiced_ratio:.0%} was voiced"
    )


def test_frame_count_matches_spectrogram():
    """Frame count must exactly match the spectrogram formula."""
    n_fft = 2048
    hop_size = n_fft // 4

    for duration in (0.5, 1.0, 2.5):
        samples = _make_sine(200.0, duration)
        f0 = compute_f0(samples, 44100, n_fft=n_fft, hop_size=hop_size)
        expected = max(0, (len(samples) - n_fft) // hop_size + 1)
        assert len(f0) == expected, (
            f"duration={duration}s: got {len(f0)} frames, expected {expected}"
        )


def test_short_audio_returns_empty():
    """Audio shorter than n_fft should return an empty array."""
    samples = np.zeros(100, dtype=np.float32)
    f0 = compute_f0(samples, 44100)
    assert len(f0) == 0
    assert f0.dtype == np.float32


def test_custom_floor_ceil():
    """Custom floor/ceil should restrict detected F0 values."""
    samples = _make_sine(200.0, 1.0)
    f0 = compute_f0(samples, 44100, f0_floor=150.0, f0_ceil=250.0)
    voiced = f0[f0 > 0]
    if len(voiced) > 0:
        assert voiced.min() >= 150.0, f"F0 below floor: {voiced.min():.1f}"
        assert voiced.max() <= 250.0, f"F0 above ceil: {voiced.max():.1f}"
