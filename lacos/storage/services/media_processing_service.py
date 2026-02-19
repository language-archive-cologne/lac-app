"""Service for generating pre-computed audio visualization artifacts.

Uses BBC's audiowaveform CLI to pre-compute peak data that WaveSurfer.js
can load instantly, avoiding client-side decoding of large audio files.
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from botocore.exceptions import ClientError
from PIL import Image

from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)

AUDIOWAVEFORM_BIN = "audiowaveform"
FFPROBE_BIN = "ffprobe"
FFMPEG_BIN = "ffmpeg"
SPECTROGRAM_STYLE_VERSION = "2"
SPECTROGRAM_DATA_VERSION = "1"
SPECTROGRAM_WIDTH = 1200
SPECTROGRAM_HEIGHT = 256


class MediaProcessingService:
    """Generate and manage audio visualization sidecars for audio files."""

    def __init__(self, bucket_service: BucketService | None = None) -> None:
        self.bucket_service = bucket_service or BucketService()

    def generate_peaks(self, bucket: str, s3_key: str) -> dict:
        """Download audio from S3 and generate peaks + spectrogram sidecars.

        Returns dict with 'success', sidecar keys, and optional 'error'.
        """
        peaks_key = self._peaks_key(s3_key)
        spectrogram_key = self._spectrogram_key(s3_key)
        spectrogram_data_key = self._spectrogram_data_key(s3_key)

        # Idempotency: skip if all sidecars already match the source ETag.
        source_etag = self._get_source_etag(bucket, s3_key)
        if not source_etag:
            return {"success": False, "error": f"Source file not found: {s3_key}"}

        peaks_current = self._artifact_is_current(bucket, peaks_key, source_etag)
        spectrogram_current = self._spectrogram_is_current(
            bucket,
            spectrogram_key,
            source_etag,
        )
        spectrogram_data_current = self._spectrogram_data_is_current(
            bucket,
            spectrogram_data_key,
            source_etag,
        )

        if peaks_current and spectrogram_current and spectrogram_data_current:
            logger.info("Audio derivatives already current for %s/%s", bucket, s3_key)
            return {
                "success": True,
                "peaks_key": peaks_key,
                "spectrogram_key": spectrogram_key,
                "spectrogram_data_key": spectrogram_data_key,
                "skipped": True,
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / Path(s3_key).name
            peaks_output_path = tmp_path / "peaks.json"
            spectrogram_output_path = tmp_path / "spectrogram.png"
            spectrogram_data_output_path = tmp_path / "spectrogram.json"

            # Download source audio
            try:
                self.bucket_service.s3_client.download_file(
                    bucket, s3_key, str(input_path)
                )
            except ClientError as exc:
                logger.error("Failed to download %s/%s: %s", bucket, s3_key, exc)
                return {"success": False, "error": f"Download failed: {exc}"}

            # Get duration for adaptive resolution
            duration = self._get_duration(input_path)
            if duration <= 0:
                return {"success": False, "error": "Could not determine audio duration"}

            if not peaks_current:
                # Generate waveform peaks sidecar.
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

            if not spectrogram_current or not spectrogram_data_current:
                # Generate spectrogram source image for sidecars.
                try:
                    self._run_ffmpeg_spectrogram(input_path, spectrogram_output_path)
                except subprocess.CalledProcessError as exc:
                    logger.error("ffmpeg spectrogram failed for %s: %s", s3_key, exc.stderr)
                    return {"success": False, "error": f"ffmpeg spectrogram error: {exc.stderr}"}
                except FileNotFoundError:
                    logger.error("ffmpeg binary not found")
                    return {"success": False, "error": "ffmpeg not installed"}

                if not spectrogram_current:
                    try:
                        spectrogram_bytes = spectrogram_output_path.read_bytes()
                    except FileNotFoundError as exc:
                        return {"success": False, "error": f"Failed to read spectrogram output: {exc}"}

                    try:
                        self.bucket_service.s3_client.put_object(
                            Bucket=bucket,
                            Key=spectrogram_key,
                            Body=spectrogram_bytes,
                            ContentType="image/png",
                            Metadata={
                                "source-etag": source_etag,
                                "spectrogram-style-version": SPECTROGRAM_STYLE_VERSION,
                            },
                        )
                    except ClientError as exc:
                        logger.error("Failed to upload spectrogram for %s: %s", s3_key, exc)
                        return {"success": False, "error": f"Upload failed: {exc}"}

                if not spectrogram_data_current:
                    try:
                        spectrogram_data = self._transform_spectrogram_for_wavesurfer(
                            spectrogram_output_path,
                            spectrogram_data_output_path,
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to generate spectrogram JSON for %s: %s",
                            s3_key,
                            exc,
                        )
                        return {"success": False, "error": f"Failed to generate spectrogram data: {exc}"}

                    try:
                        self.bucket_service.s3_client.put_object(
                            Bucket=bucket,
                            Key=spectrogram_data_key,
                            Body=spectrogram_data,
                            ContentType="application/json",
                            Metadata={
                                "source-etag": source_etag,
                                "spectrogram-style-version": SPECTROGRAM_STYLE_VERSION,
                                "spectrogram-data-version": SPECTROGRAM_DATA_VERSION,
                            },
                        )
                    except ClientError as exc:
                        logger.error("Failed to upload spectrogram data for %s: %s", s3_key, exc)
                        return {"success": False, "error": f"Upload failed: {exc}"}

        logger.info(
            "Generated audio derivatives for %s/%s -> peaks=%s spectrogram=%s spectrogram_data=%s",
            bucket,
            s3_key,
            peaks_key,
            spectrogram_key,
            spectrogram_data_key,
        )
        return {
            "success": True,
            "peaks_key": peaks_key,
            "spectrogram_key": spectrogram_key,
            "spectrogram_data_key": spectrogram_data_key,
        }

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

    def _run_ffmpeg_spectrogram(self, input_path: Path, output_path: Path) -> None:
        """Render a static spectrogram image from an audio file."""
        cmd = [
            FFMPEG_BIN,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-lavfi",
            (
                "showspectrumpic="
                f"s={SPECTROGRAM_WIDTH}x{SPECTROGRAM_HEIGHT}:"
                "legend=disabled:"
                "color=intensity:"
                "saturation=0:"
                "scale=log:"
                "fscale=lin:"
                "gain=3:"
                "drange=70"
            ),
            "-frames:v",
            "1",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)

    def _transform_spectrogram_for_wavesurfer(
        self,
        image_path: Path,
        output_path: Path,
    ) -> bytes:
        """Convert spectrogram image into WaveSurfer frequency matrix JSON."""
        with Image.open(image_path) as image:
            grayscale = image.convert("L")
            if grayscale.size != (SPECTROGRAM_WIDTH, SPECTROGRAM_HEIGHT):
                grayscale = grayscale.resize(
                    (SPECTROGRAM_WIDTH, SPECTROGRAM_HEIGHT),
                    Image.Resampling.BILINEAR,
                )

            width, height = grayscale.size
            pixels = grayscale.load()

            # WaveSurfer expects [time_slice][frequency_bin], low->high frequency.
            frequency_data = []
            for x_pos in range(width):
                column = [int(pixels[x_pos, y_pos]) for y_pos in range(height - 1, -1, -1)]
                frequency_data.append(column)

        output_path.write_text(json.dumps(frequency_data, separators=(",", ":")))
        return output_path.read_bytes()

    def _transform_peaks_for_wavesurfer(
        self, raw_json: dict, duration: float
    ) -> dict:
        """Transform audiowaveform JSON to WaveSurfer-compatible format.

        audiowaveform outputs: {version, channels, sample_rate, samples_per_pixel,
                                bits, length, data}
        WaveSurfer expects: {data: [...peaks], duration: float}
        """
        data = raw_json.get("data", [])
        channels = raw_json.get("channels", 1)
        bits = raw_json.get("bits", 8)
        max_val = (2 ** (bits - 1)) - 1 if bits > 0 else 127

        # Normalize to [-1, 1] range
        normalized = [round(v / max_val, 4) for v in data]

        return {
            "data": normalized,
            "channels": channels,
            "duration": round(duration, 3),
            "sample_rate": raw_json.get("sample_rate", 0),
            "samples_per_pixel": raw_json.get("samples_per_pixel", 0),
        }

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

    def _peaks_key(self, s3_key: str) -> str:
        """Derive peaks S3 key: recording.wav -> recording.wav.peaks.json"""
        return f"{s3_key}.peaks.json"

    def _spectrogram_key(self, s3_key: str) -> str:
        """Derive spectrogram S3 key: recording.wav -> recording.wav.spectrogram.png"""
        return f"{s3_key}.spectrogram.png"

    def _spectrogram_data_key(self, s3_key: str) -> str:
        """Derive spectrogram data S3 key: recording.wav -> recording.wav.spectrogram.json"""
        return f"{s3_key}.spectrogram.json"

    def _get_source_etag(self, bucket: str, s3_key: str) -> str | None:
        """Get ETag of the source audio file."""
        info = self.bucket_service.get_file_info(bucket, s3_key)
        if info.get("success"):
            return info.get("etag", "").strip('"')
        return None

    def _artifact_is_current(
        self, bucket: str, key: str, source_etag: str
    ) -> bool:
        """Check whether a sidecar exists and matches the source file's ETag."""
        try:
            response = self.bucket_service.s3_client.head_object(
                Bucket=bucket, Key=key
            )
            stored_etag = response.get("Metadata", {}).get("source-etag", "")
            return stored_etag == source_etag
        except ClientError:
            return False

    def _artifact_exists(self, bucket: str, key: str) -> bool:
        """Check if a sidecar exists in S3 regardless of version freshness."""
        try:
            self.bucket_service.s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise

    def _spectrogram_is_current(
        self, bucket: str, spectrogram_key: str, source_etag: str
    ) -> bool:
        """Check if spectrogram exists, matches source ETag, and style version."""
        try:
            response = self.bucket_service.s3_client.head_object(
                Bucket=bucket,
                Key=spectrogram_key,
            )
            metadata = response.get("Metadata", {})
            stored_etag = metadata.get("source-etag", "")
            style_version = metadata.get("spectrogram-style-version", "")
            return (
                stored_etag == source_etag
                and style_version == SPECTROGRAM_STYLE_VERSION
            )
        except ClientError:
            return False

    def _spectrogram_data_is_current(
        self,
        bucket: str,
        spectrogram_data_key: str,
        source_etag: str,
    ) -> bool:
        """Check if spectrogram frequency data is current for the source audio."""
        try:
            response = self.bucket_service.s3_client.head_object(
                Bucket=bucket,
                Key=spectrogram_data_key,
            )
            metadata = response.get("Metadata", {})
            stored_etag = metadata.get("source-etag", "")
            style_version = metadata.get("spectrogram-style-version", "")
            data_version = metadata.get("spectrogram-data-version", "")
            return (
                stored_etag == source_etag
                and style_version == SPECTROGRAM_STYLE_VERSION
                and data_version == SPECTROGRAM_DATA_VERSION
            )
        except ClientError:
            return False

    def peaks_exist(self, bucket: str, s3_key: str) -> bool:
        """Check if peaks file already exists (any version)."""
        return self._artifact_exists(bucket, self._peaks_key(s3_key))

    def derivatives_exist(self, bucket: str, s3_key: str) -> bool:
        """Check whether peaks and both spectrogram sidecars exist."""
        return (
            self._artifact_exists(bucket, self._peaks_key(s3_key))
            and self._artifact_exists(bucket, self._spectrogram_key(s3_key))
            and self._artifact_exists(bucket, self._spectrogram_data_key(s3_key))
        )

    def derivatives_current(self, bucket: str, s3_key: str) -> bool:
        """Check whether all audio sidecars are up to date for the source file."""
        source_etag = self._get_source_etag(bucket, s3_key)
        if not source_etag:
            return False

        return (
            self._artifact_is_current(bucket, self._peaks_key(s3_key), source_etag)
            and self._spectrogram_is_current(
                bucket, self._spectrogram_key(s3_key), source_etag
            )
            and self._spectrogram_data_is_current(
                bucket, self._spectrogram_data_key(s3_key), source_etag
            )
        )
