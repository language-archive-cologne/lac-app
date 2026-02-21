"""Service for generating pre-computed audio visualization artifacts.

Uses BBC's audiowaveform CLI for peak data and numpy STFT for spectrogram
frequency bins that match WaveSurfer.js Spectrogram plugin output exactly.
"""

import gzip
import json
import logging
import os
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from botocore.exceptions import ClientError

from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)

AUDIOWAVEFORM_BIN = "audiowaveform"
FFPROBE_BIN = "ffprobe"
FFMPEG_BIN = "ffmpeg"
# FFT / mel parameters for spectrogram pipeline.
FFT_SAMPLES = 2048
N_MELS = 256
TARGET_SAMPLE_RATE = 44100
HOP_DIVISOR = 4  # hop = n_fft // 4 → 75% overlap
STFT_CHUNK_FRAMES = 2048  # STFT frames per chunk (~50 MB peak RAM per chunk)


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (np.power(10.0, mel / 2595.0) - 1.0)


def _mel_filterbank(n_mels, n_fft, sr):
    """Create triangular mel filterbank matrix [n_mels, n_fft//2+1]."""
    n_bins = n_fft // 2 + 1
    f_max = sr / 2.0
    mel_points = np.linspace(_hz_to_mel(0), _hz_to_mel(f_max), n_mels + 2)
    hz_points = _mel_to_hz(mel_points)
    bin_indices = np.floor((n_fft + 1) * hz_points / sr).astype(int)

    filterbank = np.zeros((n_mels, n_bins))
    for m in range(n_mels):
        left, center, right = bin_indices[m], bin_indices[m + 1], bin_indices[m + 2]
        if center > left:
            filterbank[m, left:center] = np.linspace(
                0, 1, center - left, endpoint=False,
            )
        filterbank[m, center] = 1.0
        if right > center:
            filterbank[m, center + 1 : right + 1] = np.linspace(
                1, 0, right - center, endpoint=False,
            )
    return filterbank


class MediaProcessingService:
    """Generate and manage audio visualization sidecars for audio files."""

    def __init__(self, bucket_service: BucketService | None = None) -> None:
        self.bucket_service = bucket_service or BucketService()

    def generate_peaks(self, bucket: str, s3_key: str, *, force: bool = False) -> dict:
        """Download audio from S3 and generate peaks + spectrogram sidecars.

        Returns dict with 'success', sidecar keys, and optional 'error'.
        """
        peaks_key = self._peaks_key(s3_key)
        spectrogram_data_key = self._spectrogram_data_key(s3_key)

        source_etag = self._get_source_etag(bucket, s3_key)
        if not source_etag:
            return {"success": False, "error": f"Source file not found: {s3_key}"}

        if not force:
            peaks_current = self._artifact_is_current(bucket, peaks_key, source_etag)
            spectrogram_data_current = self._artifact_is_current(
                bucket, spectrogram_data_key, source_etag,
            )
        else:
            peaks_current = False
            spectrogram_data_current = False

        if peaks_current and spectrogram_data_current:
            logger.info("Audio derivatives already current for %s/%s", bucket, s3_key)
            return {
                "success": True,
                "peaks_key": peaks_key,
                "spectrogram_data_key": spectrogram_data_key,
                "skipped": True,
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / Path(s3_key).name
            peaks_output_path = tmp_path / "peaks.json"

            try:
                self.bucket_service.s3_client.download_file(
                    bucket, s3_key, str(input_path)
                )
            except ClientError as exc:
                logger.error("Failed to download %s/%s: %s", bucket, s3_key, exc)
                return {"success": False, "error": f"Download failed: {exc}"}

            duration = self._get_duration(input_path)
            if duration <= 0:
                return {"success": False, "error": "Could not determine audio duration"}

            if not peaks_current:
                try:
                    self._run_audiowaveform(input_path, peaks_output_path, duration)
                except subprocess.CalledProcessError as exc:
                    logger.error("audiowaveform failed for %s: %s", s3_key, exc.stderr)
                    return {"success": False, "error": f"audiowaveform error: {exc.stderr}"}
                except FileNotFoundError:
                    logger.error("audiowaveform binary not found")
                    return {"success": False, "error": "audiowaveform not installed"}

                try:
                    raw_json = json.loads(peaks_output_path.read_text())
                except (json.JSONDecodeError, FileNotFoundError) as exc:
                    return {"success": False, "error": f"Failed to read peaks output: {exc}"}

                peaks_data = self._transform_peaks_for_wavesurfer(raw_json, duration)
                peaks_bytes = json.dumps(peaks_data, separators=(",", ":")).encode()

                try:
                    self.bucket_service.s3_client.put_object(
                        Bucket=bucket,
                        Key=peaks_key,
                        Body=peaks_bytes,
                        ContentType="application/json",
                        Metadata={"source-etag": source_etag},
                    )
                except ClientError as exc:
                    logger.error("Failed to upload peaks for %s: %s", s3_key, exc)
                    return {"success": False, "error": f"Upload failed: {exc}"}

            if not spectrogram_data_current:
                try:
                    spectrogram_data = self._compute_spectrogram(input_path)
                except Exception as exc:
                    logger.error(
                        "Failed to compute spectrogram for %s: %s", s3_key, exc,
                    )
                    return {"success": False, "error": f"Spectrogram computation failed: {exc}"}

                try:
                    self.bucket_service.s3_client.put_object(
                        Bucket=bucket,
                        Key=spectrogram_data_key,
                        Body=gzip.compress(spectrogram_data),
                        ContentType="application/octet-stream",
                        ContentEncoding="gzip",
                        Metadata={"source-etag": source_etag},
                    )
                except ClientError as exc:
                    logger.error("Failed to upload spectrogram data for %s: %s", s3_key, exc)
                    return {"success": False, "error": f"Upload failed: {exc}"}

        logger.info(
            "Generated audio derivatives for %s/%s -> peaks=%s spectrogram_data=%s",
            bucket, s3_key, peaks_key, spectrogram_data_key,
        )
        return {
            "success": True,
            "peaks_key": peaks_key,
            "spectrogram_data_key": spectrogram_data_key,
        }

    # ------------------------------------------------------------------
    # Peaks
    # ------------------------------------------------------------------

    def _run_audiowaveform(
        self, input_path: Path, output_path: Path, duration: float
    ) -> None:
        """Run audiowaveform CLI with adaptive pixels-per-second."""
        pps = int(min(100, max(20, 30000 / duration)))
        cmd = [
            AUDIOWAVEFORM_BIN,
            "-i", str(input_path),
            "-o", str(output_path),
            "--pixels-per-second", str(pps),
            "-b", "8",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)

    def _transform_peaks_for_wavesurfer(
        self, raw_json: dict, duration: float
    ) -> dict:
        """Transform audiowaveform JSON to WaveSurfer-compatible format."""
        data = raw_json.get("data", [])
        channels = raw_json.get("channels", 1)
        bits = raw_json.get("bits", 8)
        max_val = (2 ** (bits - 1)) - 1 if bits > 0 else 127

        normalized = [round(v / max_val, 4) for v in data]

        return {
            "data": normalized,
            "channels": channels,
            "duration": round(duration, 3),
            "sample_rate": raw_json.get("sample_rate", 0),
            "samples_per_pixel": raw_json.get("samples_per_pixel", 0),
        }

    # ------------------------------------------------------------------
    # Spectrogram (numpy STFT matching WaveSurfer Spectrogram plugin)
    # ------------------------------------------------------------------

    def _decode_audio_to_pcm(self, input_path: Path) -> np.ndarray:
        """Decode any audio format to mono float32 PCM via ffmpeg."""
        cmd = [
            FFMPEG_BIN,
            "-hide_banner", "-loglevel", "error",
            "-i", str(input_path),
            "-ac", "1",
            "-ar", str(TARGET_SAMPLE_RATE),
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "pipe:1",
        ]
        result = subprocess.run(
            cmd, check=True, capture_output=True, timeout=600,
        )
        return np.frombuffer(result.stdout, dtype=np.float32)

    def _compute_spectrogram(self, input_path: Path) -> bytes:
        """Compute mel-scale spectrogram with fixed 75% overlap.

        Returns binary payload: 6-byte header (uint32 LE n_frames + uint16 LE
        n_bins) followed by n_frames * n_bins raw uint8 bytes in row-major
        (frame-major) order.  The caller gzip-compresses before upload.

        Uses chunked STFT with sliding_window_view to keep peak memory
        under ~200 MB regardless of audio duration.

        Pipeline:
        1. Hann window of size FFT_SAMPLES (2048), hop = n_fft // 4
        2. RFFT → magnitude spectrum, normalized 2/N (chunked)
        3. Mel filterbank projection (N_MELS=256 bins)
        4. dB conversion: 20 * log10(max(1e-12, mel_mag))
        5. Adaptive percentile-based 0-255 scaling per file
        """
        samples = self._decode_audio_to_pcm(input_path)
        n_fft = FFT_SAMPLES
        n_samples = len(samples)

        if n_samples < n_fft:
            return b""

        window = np.hanning(n_fft).astype(np.float32)
        hop_size = max(64, n_fft // HOP_DIVISOR)
        n_frames = (n_samples - n_fft) // hop_size + 1
        mel_fb_t = _mel_filterbank(N_MELS, n_fft, TARGET_SAMPLE_RATE).T

        # Pass 1: compute mel dB in chunks, store to disk-backed array.
        db_path = None
        try:
            db_fd, db_path = tempfile.mkstemp(suffix=".f64", prefix="lac_db_")
            os.close(db_fd)
            db_mm = np.memmap(
                db_path, dtype=np.float64, mode="w+", shape=(n_frames, N_MELS),
            )

            for chunk_start in range(0, n_frames, STFT_CHUNK_FRAMES):
                chunk_end = min(chunk_start + STFT_CHUNK_FRAMES, n_frames)
                sample_start = chunk_start * hop_size
                sample_end = (chunk_end - 1) * hop_size + n_fft
                chunk = samples[sample_start:sample_end]

                frames_view = np.lib.stride_tricks.sliding_window_view(
                    chunk, n_fft,
                )[::hop_size]
                frames_view = frames_view[: chunk_end - chunk_start]

                windowed = frames_view * window
                fft_result = np.fft.rfft(windowed, n=n_fft, axis=1)
                magnitudes = (2.0 / n_fft) * np.abs(fft_result)
                mel_mag = magnitudes @ mel_fb_t
                db_mm[chunk_start:chunk_end] = 20.0 * np.log10(
                    np.maximum(mel_mag, 1e-12),
                )

            db_mm.flush()

            # Percentiles via in-place partition on the memmap.
            lower = float(np.percentile(db_mm, 5))
            upper = float(np.percentile(db_mm, 95))
            if upper - lower < 30:
                center = (upper + lower) / 2
                lower = center - 15
                upper = center + 15

            # Pass 2: scale to uint8 in chunks.
            uint8_data = np.empty((n_frames, N_MELS), dtype=np.uint8)
            for i in range(0, n_frames, STFT_CHUNK_FRAMES):
                j = min(i + STFT_CHUNK_FRAMES, n_frames)
                scaled = np.clip(
                    (db_mm[i:j] - lower) / (upper - lower) * 255.0, 0, 255,
                )
                uint8_data[i:j] = np.round(scaled).astype(np.uint8)

            header = struct.pack("<IH", n_frames, N_MELS)
            return header + uint8_data.tobytes()
        finally:
            del db_mm
            if db_path is not None:
                try:
                    os.remove(db_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Duration
    # ------------------------------------------------------------------

    def _get_duration(self, file_path: Path) -> float:
        """Use ffprobe to get duration in seconds."""
        cmd = [
            FFPROBE_BIN,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(file_path),
        ]
        try:
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True, timeout=60
            )
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("ffprobe failed for %s: %s", file_path, exc)
            return 0.0

    # ------------------------------------------------------------------
    # S3 key helpers
    # ------------------------------------------------------------------

    def _peaks_key(self, s3_key: str) -> str:
        return f"{s3_key}.peaks.json"

    def _spectrogram_data_key(self, s3_key: str) -> str:
        return f"{s3_key}.spectrogram.bin"

    # ------------------------------------------------------------------
    # Freshness checks
    # ------------------------------------------------------------------

    def _get_source_etag(self, bucket: str, s3_key: str) -> str | None:
        info = self.bucket_service.get_file_info(bucket, s3_key)
        if info.get("success"):
            return info.get("etag", "").strip('"')
        return None

    def _artifact_is_current(
        self, bucket: str, key: str, source_etag: str
    ) -> bool:
        try:
            response = self.bucket_service.s3_client.head_object(
                Bucket=bucket, Key=key
            )
            stored_etag = response.get("Metadata", {}).get("source-etag", "")
            return stored_etag == source_etag
        except ClientError:
            return False

    def _artifact_exists(self, bucket: str, key: str) -> bool:
        try:
            self.bucket_service.s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise

    def peaks_exist(self, bucket: str, s3_key: str) -> bool:
        return self._artifact_exists(bucket, self._peaks_key(s3_key))

    def derivatives_exist(self, bucket: str, s3_key: str) -> bool:
        return (
            self._artifact_exists(bucket, self._peaks_key(s3_key))
            and self._artifact_exists(bucket, self._spectrogram_data_key(s3_key))
        )

    def derivatives_current(self, bucket: str, s3_key: str) -> bool:
        source_etag = self._get_source_etag(bucket, s3_key)
        if not source_etag:
            return False

        return (
            self._artifact_is_current(bucket, self._peaks_key(s3_key), source_etag)
            and self._artifact_is_current(
                bucket, self._spectrogram_data_key(s3_key), source_etag
            )
        )
