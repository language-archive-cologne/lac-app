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


def _local_minima(cmnd: np.ndarray, min_lag: int, max_lag: int) -> np.ndarray:
    """Return lag indices of local minima within [min_lag, max_lag)."""
    if max_lag - min_lag < 3:
        return np.array([], dtype=np.int32)

    region = cmnd[min_lag:max_lag]
    prev_vals = region[:-2]
    cur_vals = region[1:-1]
    next_vals = region[2:]
    mins = np.where((cur_vals <= prev_vals) & (cur_vals <= next_vals))[0]
    return (mins + min_lag + 1).astype(np.int32)


def _extract_candidates(
    cmnd: np.ndarray,
    sample_rate: int,
    min_lag: int,
    max_lag: int,
    f0_floor: float,
    f0_ceil: float,
    threshold: float,
    max_candidates: int,
) -> list[tuple[float, float]]:
    """Extract voiced F0 candidates as (frequency_hz, cmnd_cost)."""
    # Accept a broader candidate pool than the hard voicing threshold and let
    # path optimization choose stable trajectories.
    relaxed_threshold = min(0.9, max(threshold * 2.2, threshold))
    candidates: list[tuple[float, float]] = []
    seen: set[int] = set()

    primary_tau = _absolute_threshold(cmnd, threshold, min_lag, max_lag)
    primary_ref = float(primary_tau) if primary_tau > 0 else 0.0
    if primary_tau > 0:
        refined = _parabolic_interpolation(cmnd, primary_tau)
        if refined > 0:
            freq = sample_rate / refined
            if f0_floor <= freq <= f0_ceil:
                # Favor YIN's first threshold-crossing candidate to avoid
                # selecting subharmonics as the main path.
                candidates.append((float(freq), float(cmnd[primary_tau]) - 0.05))
                seen.add(int(round(freq * 10)))

    for tau in _local_minima(cmnd, min_lag, max_lag):
        cmnd_val = float(cmnd[tau])
        if cmnd_val > relaxed_threshold:
            continue
        if primary_ref > 0.0 and float(tau) > primary_ref * 1.6:
            # Lower-frequency subharmonics usually appear at much larger lags.
            continue
        refined = _parabolic_interpolation(cmnd, int(tau))
        if refined <= 0:
            continue
        freq = sample_rate / refined
        if f0_floor <= freq <= f0_ceil:
            key = int(round(freq * 10))
            if key not in seen:
                candidates.append((float(freq), cmnd_val))
                seen.add(key)

    # Fallback: if no local minimum survived, consider the best lag in range.
    if not candidates:
        rel = int(np.argmin(cmnd[min_lag:max_lag]))
        tau = min_lag + rel
        cmnd_val = float(cmnd[tau])
        if cmnd_val <= relaxed_threshold:
            refined = _parabolic_interpolation(cmnd, tau)
            if refined > 0:
                freq = sample_rate / refined
                if f0_floor <= freq <= f0_ceil:
                    candidates.append((float(freq), cmnd_val))

    candidates.sort(key=lambda x: x[1])
    return candidates[:max(1, max_candidates)]


def _viterbi_select_path(
    frame_candidates: list[list[tuple[float, float]]],
    frame_is_silent: np.ndarray,
    f0_floor: float,
    octave_cost: float,
    octave_jump_cost: float,
    voiced_unvoiced_cost: float,
) -> np.ndarray:
    """Select the globally best F0 path with Praat-like transition costs."""
    n_frames = len(frame_candidates)
    if n_frames == 0:
        return np.array([], dtype=np.float32)

    all_states: list[list[tuple[float, float]]] = []
    for i in range(n_frames):
        # State tuple: (frequency_hz, emission_cost)
        unvoiced_cost = 0.0 if frame_is_silent[i] else voiced_unvoiced_cost
        states = [(0.0, unvoiced_cost)]
        for freq, cmnd_val in frame_candidates[i]:
            # Penalize very high frequencies similarly to Praat's octave cost.
            oct_penalty = octave_cost * max(0.0, np.log2(freq / max(f0_floor, 1e-6)))
            states.append((freq, cmnd_val + float(oct_penalty)))
        all_states.append(states)

    dp: list[np.ndarray] = []
    back: list[np.ndarray] = []

    first = np.array([cost for _, cost in all_states[0]], dtype=np.float64)
    dp.append(first)
    back.append(np.full(len(first), -1, dtype=np.int32))

    for t in range(1, n_frames):
        prev_states = all_states[t - 1]
        curr_states = all_states[t]
        prev_costs = dp[t - 1]
        curr_costs = np.full(len(curr_states), np.inf, dtype=np.float64)
        curr_back = np.full(len(curr_states), -1, dtype=np.int32)

        for ci, (curr_f, curr_emit) in enumerate(curr_states):
            best_cost = np.inf
            best_pi = -1
            for pi, (prev_f, _) in enumerate(prev_states):
                trans = 0.0
                if prev_f == 0.0 and curr_f == 0.0:
                    trans = 0.0
                elif prev_f == 0.0 or curr_f == 0.0:
                    trans = voiced_unvoiced_cost
                else:
                    trans = octave_jump_cost * abs(np.log2(curr_f / prev_f))
                total = prev_costs[pi] + trans + curr_emit
                if total < best_cost:
                    best_cost = total
                    best_pi = pi
            curr_costs[ci] = best_cost
            curr_back[ci] = best_pi

        dp.append(curr_costs)
        back.append(curr_back)

    path = np.zeros(n_frames, dtype=np.float32)
    state_idx = int(np.argmin(dp[-1]))
    for t in range(n_frames - 1, -1, -1):
        path[t] = float(all_states[t][state_idx][0])
        state_idx = int(back[t][state_idx])
        if state_idx < 0 and t > 0:
            state_idx = 0
    return path


def _post_process_f0(
    f0: np.ndarray,
    *,
    min_voiced_run: int,
    max_unvoiced_gap: int,
) -> np.ndarray:
    """Remove very short voiced spikes and fill tiny unvoiced gaps."""
    out = f0.astype(np.float32, copy=True)
    n = len(out)
    if n == 0:
        return out

    # 1) Remove short voiced runs.
    i = 0
    while i < n:
        if out[i] <= 0:
            i += 1
            continue
        j = i + 1
        while j < n and out[j] > 0:
            j += 1
        if j - i < max(1, min_voiced_run):
            out[i:j] = 0.0
        i = j

    # 2) Fill short unvoiced gaps between voiced runs with linear interpolation.
    i = 0
    while i < n:
        if out[i] > 0:
            i += 1
            continue
        j = i + 1
        while j < n and out[j] <= 0:
            j += 1
        gap_len = j - i
        left = i - 1
        right = j
        if (
            gap_len > 0
            and gap_len <= max(0, max_unvoiced_gap)
            and left >= 0
            and right < n
            and out[left] > 0
            and out[right] > 0
        ):
            step = (out[right] - out[left]) / float(gap_len + 1)
            for k in range(gap_len):
                out[i + k] = out[left] + step * (k + 1)
        i = j

    # 3) Light median smoothing within each voiced run.
    i = 0
    while i < n:
        if out[i] <= 0:
            i += 1
            continue
        j = i + 1
        while j < n and out[j] > 0:
            j += 1
        segment = out[i:j].copy()
        if len(segment) >= 3:
            smoothed = segment.copy()
            for s in range(1, len(segment) - 1):
                smoothed[s] = float(np.median(segment[s - 1 : s + 2]))
            out[i:j] = smoothed
        i = j

    return out


def compute_f0(
    samples: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop_size: int | None = None,
    f0_floor: float = F0_FLOOR,
    f0_ceil: float = F0_CEIL,
    threshold: float = 0.22,
    silence_threshold: float = 0.03,
    octave_cost: float = 0.01,
    octave_jump_cost: float = 0.35,
    voiced_unvoiced_cost: float = 0.14,
    max_candidates: int = 5,
    post_process: bool = True,
    min_voiced_run: int = 2,
    max_unvoiced_gap: int = 2,
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
    silence_threshold : float
        Relative frame amplitude threshold (vs. global max) for silence gating.
    octave_cost : float
        Penalty for higher octave candidates.
    octave_jump_cost : float
        Penalty for frame-to-frame octave jumps.
    voiced_unvoiced_cost : float
        Penalty for voiced/unvoiced state transitions.
    max_candidates : int
        Number of voiced candidates retained per frame.
    post_process : bool
        Apply short-run cleanup and tiny-gap interpolation.
    min_voiced_run : int
        Short voiced runs below this length are removed.
    max_unvoiced_gap : int
        Unvoiced gaps up to this length are linearly interpolated.

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

    frame_candidates: list[list[tuple[float, float]]] = [[] for _ in range(n_frames)]
    frame_is_silent = np.zeros(n_frames, dtype=bool)
    global_peak = float(np.max(np.abs(samples))) if len(samples) else 0.0

    for i in range(n_frames):
        start = i * hop_size
        frame = samples[start : start + n_fft]

        frame_peak = float(np.max(np.abs(frame)))
        silent = (
            global_peak < 1e-12
            or frame_peak < max(0.0, silence_threshold) * global_peak
            or frame_peak < 1e-6
        )
        frame_is_silent[i] = silent
        if silent:
            continue

        d = _difference_function(frame, max_lag)
        cmnd = _cumulative_mean_normalized_difference(d)
        frame_candidates[i] = _extract_candidates(
            cmnd,
            sample_rate,
            min_lag,
            max_lag,
            f0_floor,
            f0_ceil,
            threshold,
            max_candidates,
        )

    f0 = _viterbi_select_path(
        frame_candidates,
        frame_is_silent,
        f0_floor,
        octave_cost,
        octave_jump_cost,
        voiced_unvoiced_cost,
    )
    if post_process:
        f0 = _post_process_f0(
            f0,
            min_voiced_run=min_voiced_run,
            max_unvoiced_gap=max_unvoiced_gap,
        )
    return f0.astype(np.float32, copy=False)
