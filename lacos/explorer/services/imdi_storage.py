"""Discover and read IMDI files from S3/MinIO storage."""

from __future__ import annotations

import logging

from botocore.exceptions import BotoCoreError
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ImdiStorageService:
    """Thin wrapper around an S3 client for IMDI file operations."""

    def __init__(self, s3_client):
        self.s3_client = s3_client

    def discover_imdi_files(self, bucket: str, prefix: str) -> list[str]:
        """List all ``.imdi`` file keys under the given prefix."""
        keys: list[str] = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(".imdi"):
                    keys.append(key)
        return keys

    def read_imdi_file(self, bucket: str, key: str) -> bytes | None:
        """Read an IMDI object from S3 and return bytes, or ``None`` on failure."""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError, KeyError, RuntimeError):
            logger.warning(
                "Failed to read IMDI file s3://%s/%s",
                bucket,
                key,
                exc_info=True,
            )
            return None

    def find_root_imdi(self, keys: list[str], prefix: str) -> str | None:
        """Pick the most likely root IMDI file from discovered keys."""
        del prefix  # reserved for future heuristics
        if not keys:
            return None
        return sorted(keys, key=lambda key: (key.count("/"), key))[0]
