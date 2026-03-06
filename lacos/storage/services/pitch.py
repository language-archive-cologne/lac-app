"""YIN-based F0 (fundamental frequency) pitch extraction.

Pure numpy implementation — no external audio libraries required.
Produces frames aligned with the spectrogram pipeline (same n_fft and hop_size).

References
----------
De Cheveigné, A., & Kawahara, H. (2002). "YIN, a fundamental frequency
estimator for speech and music." JASA 111(4), 1917–1930.
"""

from __future__ import annotations

import numpy as np

# Default pitch range suitable for human speech.
F0_FLOOR: float = 60.0
F0_CEIL: float = 450.0


def _difference_function(frame: np.ndarray, max_lag: int) -> np.ndarray:
    """Compute the YIN difference function d(tau) for lags 0..max_lag-1.

    Uses the autocorrelation trick via FFT for O(N log N) performance
    instead of the naive O(N * max_lag) double loop.
    """
    n = len(frame)
    fft_size = 1
    while fft_size < 2 * n:
        fft_size *= 2

    # Power terms computed via cumulative sum.
    frame64 = frame.astype(np.float64)
    x_sq = frame64 ** 2
    cum = np.concatenate(([0.0], np.cumsum(x_sq)))

    # Autocorrelation via FFT.
    fft_frame = np.fft.rfft(frame64, n=fft_size)
    acf_full = np.fft.irfft(fft_frame * np.conj(fft_frame))
    acf = acf_full[:max_lag]

    # d(tau) = cum[W-tau] + (cum[W] - cum[tau]) - 2 * acf(tau)
    taus = np.arange(max_lag)
    d = cum[n - taus] + (cum[n] - cum[taus]) - 2.0 * acf
    d[0] = 0.0
    return d


def _cumulative_mean_normalized_difference(d: np.ndarray) -> np.ndarray:
    """Step 2: CMND — normalize d(tau) by running mean."""
    n = len(d)
    out = np.empty(n, dtype=np.float64)
    out[0] = 1.0
    running_sum = 0.0
    for tau in range(1, n):
        running_sum += d[tau]
        out[tau] = d[tau] * tau / running_sum if running_sum > 0 else 1.0
    return out


def _absolute_threshold(
    cmnd: np.ndarray, threshold: float, min_lag: int, max_lag: int,
) -> int:
    """Step 3: find the first lag in [min_lag, max_lag) where CMND < threshold.

    Returns the lag index, or 0 if no valley is found.
    """
    for tau in range(min_lag, max_lag):
        if cmnd[tau] < threshold:
            # Walk to the local minimum.
            while tau + 1 < max_lag and cmnd[tau + 1] < cmnd[tau]:
                tau += 1
            return tau
    return 0


def _parabolic_interpolation(cmnd: np.ndarray, tau: int) -> float:
    """Step 5: refine the lag estimate with parabolic interpolation."""
    if tau < 1 or tau >= len(cmnd) - 1:
        return float(tau)

    s0 = cmnd[tau - 1]
    s1 = cmnd[tau]
    s2 = cmnd[tau + 1]
    denom = 2.0 * (2.0 * s1 - s2 - s0)
    if abs(denom) < 1e-12:
        return float(tau)
    return tau + (s0 - s2) / denom


def compute_f0(
    samples: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop_size: int | None = None,
    f0_floor: float = F0_FLOOR,
    f0_ceil: float = F0_CEIL,
    threshold: float = 0.15,
) -> np.ndarray:
    """Extract F0 contour from mono audio using the YIN algorithm.

    Parameters
    ----------
    samples : np.ndarray
        Mono float32 audio samples.
    sample_rate : int
        Sample rate in Hz.
    n_fft : int
        Analysis window size (must match spectrogram).
    hop_size : int | None
        Hop between frames. Defaults to ``n_fft // 4``.
    f0_floor : float
        Lowest detectable F0 in Hz.
    f0_ceil : float
        Highest detectable F0 in Hz.
    threshold : float
        YIN aperiodicity threshold (lower = stricter voicing decision).

    Returns
    -------
    np.ndarray
        Float32 array of length ``max(0, (len(samples) - n_fft) // hop_size + 1)``.
        Positive values are F0 in Hz; ``0.0`` marks unvoiced frames.
    """
    if hop_size is None:
        hop_size = n_fft // 4

    n_samples = len(samples)
    n_frames = max(0, (n_samples - n_fft) // hop_size + 1)

    if n_frames == 0:
        return np.array([], dtype=np.float32)

    # Lag search bounds derived from pitch range.
    min_lag = max(2, int(sample_rate / f0_ceil))
    max_lag = min(n_fft, int(sample_rate / f0_floor) + 1)

    if max_lag <= min_lag:
        return np.zeros(n_frames, dtype=np.float32)

    f0 = np.zeros(n_frames, dtype=np.float32)

    for i in range(n_frames):
        start = i * hop_size
        frame = samples[start : start + n_fft]

        # Skip near-silent frames early.
        if np.max(np.abs(frame)) < 1e-6:
            continue

        d = _difference_function(frame, max_lag)
        cmnd = _cumulative_mean_normalized_difference(d)

        # Search only within [min_lag, max_lag).
        tau = _absolute_threshold(cmnd, threshold, min_lag, max_lag)
        if tau == 0:
            continue  # unvoiced

        refined = _parabolic_interpolation(cmnd, tau)

        if refined <= 0:
            continue

        freq = sample_rate / refined

        if f0_floor <= freq <= f0_ceil:
            f0[i] = freq

    return f0
