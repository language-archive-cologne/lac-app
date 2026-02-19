"""Service for generating waveform peak data from audio files.

Uses BBC's audiowaveform CLI to pre-compute peak data that WaveSurfer.js
can load instantly, avoiding client-side decoding of large audio files.
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from botocore.exceptions import ClientError

from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)

AUDIOWAVEFORM_BIN = "audiowaveform"
FFPROBE_BIN = "ffprobe"


class MediaProcessingService:
    """Generate and manage waveform peak data for audio files."""

    def __init__(self, bucket_service: BucketService | None = None) -> None:
        self.bucket_service = bucket_service or BucketService()

    def generate_peaks(self, bucket: str, s3_key: str) -> dict:
        """Download audio from S3, generate peaks JSON, upload result.

        Returns dict with 'success' and optional 'peaks_key' or 'error'.
        """
        peaks_key = self._peaks_key(s3_key)

        # Idempotency: check if peaks already exist with matching source ETag
        source_etag = self._get_source_etag(bucket, s3_key)
        if not source_etag:
            return {"success": False, "error": f"Source file not found: {s3_key}"}

        if self._peaks_are_current(bucket, peaks_key, source_etag):
            logger.info("Peaks already current for %s/%s", bucket, s3_key)
            return {"success": True, "peaks_key": peaks_key, "skipped": True}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / Path(s3_key).name
            output_path = tmp_path / "peaks.json"

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

            # Generate peaks
            try:
                self._run_audiowaveform(input_path, output_path, duration)
            except subprocess.CalledProcessError as exc:
                logger.error("audiowaveform failed for %s: %s", s3_key, exc.stderr)
                return {"success": False, "error": f"audiowaveform error: {exc.stderr}"}
            except FileNotFoundError:
                logger.error("audiowaveform binary not found")
                return {"success": False, "error": "audiowaveform not installed"}

            # Transform to WaveSurfer format and upload
            try:
                raw_json = json.loads(output_path.read_text())
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

        logger.info("Generated peaks for %s/%s -> %s", bucket, s3_key, peaks_key)
        return {"success": True, "peaks_key": peaks_key}

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

    def _get_source_etag(self, bucket: str, s3_key: str) -> str | None:
        """Get ETag of the source audio file."""
        info = self.bucket_service.get_file_info(bucket, s3_key)
        if info.get("success"):
            return info.get("etag", "").strip('"')
        return None

    def _peaks_are_current(
        self, bucket: str, peaks_key: str, source_etag: str
    ) -> bool:
        """Check if peaks exist and match the source file's ETag."""
        try:
            response = self.bucket_service.s3_client.head_object(
                Bucket=bucket, Key=peaks_key
            )
            stored_etag = response.get("Metadata", {}).get("source-etag", "")
            return stored_etag == source_etag
        except ClientError:
            return False

    def peaks_exist(self, bucket: str, s3_key: str) -> bool:
        """Check if peaks file already exists (any version)."""
        peaks_key = self._peaks_key(s3_key)
        try:
            self.bucket_service.s3_client.head_object(Bucket=bucket, Key=peaks_key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise
