"""Shared fixtures for the media audit tests: a small in-memory S3 and BLAM data."""

import io
import json
import struct
from datetime import UTC
from datetime import datetime

import pytest
from botocore.exceptions import ClientError

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.services.media_processing_service import DERIVATIVE_FORMAT_VERSION

BUCKET = "lac-test"
MODIFIED = datetime(2026, 10, 1, tzinfo=UTC)


def wav_header(duration: float, byte_rate: int = 88200) -> tuple[bytes, int]:
    """Return a 44-byte WAV header and the size of the whole file."""
    data_size = int(duration * byte_rate)
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, byte_rate // 2, byte_rate, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )
    return header, len(header) + data_size


def spectrogram_frames(duration: float) -> int:
    return (int(duration * 44100) - 2048) // 512 + 1


class FakeS3:
    """Store objects by (bucket, key); answer head_object and ranged get_object.

    An object stores only its first bytes; ``size`` is the size S3 reports.
    """

    def __init__(self):
        self.objects: dict[tuple[str, str], dict] = {}

    def put(
        self,
        key,
        *,
        etag="abc",
        metadata=None,
        body=b"",
        size=None,
        encoding=None,
        bucket=BUCKET,
    ):
        obj = {
            "ETag": f'"{etag}"',
            "Metadata": metadata or {},
            "LastModified": MODIFIED,
            "ContentLength": len(body) if size is None else size,
            "Body": body,
        }
        if encoding:
            obj["ContentEncoding"] = encoding
        self.objects[(bucket, key)] = obj

    def put_wav(self, key, *, duration=10.0, etag="abc"):
        header, size = wav_header(duration)
        self.put(key, etag=etag, body=header, size=size)

    def put_derivatives(
        self,
        content_key,
        *,
        duration=10.0,
        source_etag="abc",
        version=None,
        pitch=True,
        metadata=True,
    ):
        meta = (
            {
                "source-etag": source_etag,
                "format-version": str(version or DERIVATIVE_FORMAT_VERSION),
            }
            if metadata
            else {"mtime": "1777379171.3"}
        )
        base = content_key.replace("/content/", "/derivatives/")
        peaks = json.dumps(
            {
                "data": [0.1] * 400,
                "channels": 1,
                "duration": duration,
                "sample_rate": 44100,
                "samples_per_pixel": 441,
            },
            separators=(",", ":"),
        ).encode()
        self.put(f"{base}.peaks.json", metadata=meta, body=peaks)
        n_frames = spectrogram_frames(duration)
        self.put(
            f"{base}.spectrogram.bin",
            metadata=meta,
            body=struct.pack("<IH", n_frames, 256),
            size=6 + n_frames * 256,
        )
        if pitch:
            self.put(
                f"{base}.pitch.bin",
                metadata=meta,
                body=struct.pack("<IHff", n_frames, 512, 50.0, 500.0),
                size=14 + 4 * n_frames,
            )

    def _get(self, Bucket, Key):
        try:
            return self.objects[(Bucket, Key)]
        except KeyError:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject") from None

    def head_object(self, Bucket, Key):
        obj = self._get(Bucket, Key)
        return {k: v for k, v in obj.items() if k != "Body"}

    def get_object(self, Bucket, Key, Range=None):
        body = self._get(Bucket, Key)["Body"]
        if Range:
            start, _, end = Range.removeprefix("bytes=").partition("-")
            body = body[-int(end) :] if not start else body[int(start) : int(end) + 1]
        return {"Body": io.BytesIO(body)}


class FakeStorage:
    def __init__(self, s3):
        self.s3_client = s3


@pytest.fixture
def fake_s3():
    return FakeS3()


@pytest.fixture
def media_service(fake_s3):
    from lacos.storage.services.media_processing_service import MediaProcessingService

    return MediaProcessingService(bucket_service=FakeStorage(fake_s3))


def content_key(file_name):
    return f"col/bundle/content/{file_name}"


@pytest.fixture
def resolve_by_name(fake_s3, monkeypatch):
    """Resolve a resource to col/bundle/content/<file_name> when that object exists."""

    def resolve(resource_service, resource, bundle, collection, **kwargs):
        key = content_key(resource.file_name)
        if (BUCKET, key) not in fake_s3.objects:
            return None
        return {"bucket": BUCKET, "key": key, "url": f"https://s3/{key}"}

    monkeypatch.setattr(
        "lacos.explorer.views.utils.storage.resolve_resource_to_presigned",
        resolve,
    )
    return resolve


def make_collection(identifier="totoli"):
    return Collection.objects.create(identifier=identifier)


def make_bundle(collection, identifier="bundle-1"):
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Bundle",
        description="Bundle",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=collection
    )
    BundleResources.objects.create(bundle=bundle)
    return bundle


def add_audio(bundle, file_name, mime_type="audio/x-wav"):
    resource = MediaResource.objects.create(
        file_name=file_name,
        file_pid=f"https://hdl.handle.net/test/{file_name}",
        mime_type=mime_type,
        file_length="1",
    )
    bundle.resources.first().bundle_media_resources.add(resource)
    return resource


def add_elan(bundle, file_name):
    resource = WrittenResource.objects.create(
        file_name=file_name,
        file_pid=f"https://hdl.handle.net/test/{file_name}",
        mime_type="text/x-eaf+xml",
    )
    bundle.resources.first().bundle_written_resources.add(resource)
    return resource


def elan_xml(media_url=None):
    descriptor = (
        f'<MEDIA_DESCRIPTOR MEDIA_URL="{media_url}" MIME_TYPE="audio/x-wav"/>'
        if media_url
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ANNOTATION_DOCUMENT>"
        f'<HEADER MEDIA_FILE="" TIME_UNITS="milliseconds">{descriptor}</HEADER>'
        "<TIME_ORDER/></ANNOTATION_DOCUMENT>"
    ).encode()
