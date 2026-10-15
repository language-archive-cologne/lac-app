import pytest

from lacos.storage.models import MediaDerivativeStatus
from lacos.storage.models import S3ResourceLocation
from lacos.storage.services.media_derivative_recorder import collection_for_object
from lacos.storage.services.media_derivative_recorder import inspect_derivatives
from lacos.storage.services.media_derivative_recorder import record_check
from lacos.storage.services.media_derivative_recorder import record_generation

from .conftest import BUCKET
from .conftest import add_audio
from .conftest import content_key
from .conftest import make_bundle
from .conftest import make_collection

KEY = content_key("a.wav")


DERIVATIVES = "col/bundle/derivatives/a.wav"


def test_files_that_fit_the_audio_work(fake_s3, media_service):
    fake_s3.put_wav(KEY, duration=10.0)
    fake_s3.put_derivatives(KEY, duration=10.0)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "works"
    assert result["problems"] == ""
    assert result["audio_duration"] == pytest.approx(10.0)
    assert result["peaks_last_modified"] is not None


def test_files_without_metadata_work_when_they_fit(fake_s3, media_service):
    """Files uploaded outside the app have no source-etag or format-version."""
    fake_s3.put_wav(KEY)
    fake_s3.put_derivatives(KEY, metadata=False)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "works"
    assert result["format_version"] is None


def test_a_different_source_etag_alone_does_not_break(fake_s3, media_service):
    fake_s3.put_wav(KEY, etag="new-upload-2")
    fake_s3.put_derivatives(KEY, source_etag="old-upload-5")

    assert inspect_derivatives(media_service, BUCKET, KEY)["status"] == "works"


def test_pitch_is_optional(fake_s3, media_service):
    fake_s3.put_wav(KEY)
    fake_s3.put_derivatives(KEY, pitch=False)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "works"
    assert result["pitch_last_modified"] is None


def test_missing_without_spectrogram(fake_s3, media_service):
    fake_s3.put_wav(KEY)
    fake_s3.put_derivatives(KEY)
    del fake_s3.objects[(BUCKET, f"{DERIVATIVES}.spectrogram.bin")]

    assert inspect_derivatives(media_service, BUCKET, KEY)["status"] == "missing"


def test_source_missing(media_service):
    assert inspect_derivatives(media_service, BUCKET, KEY)["status"] == "source_missing"


def test_derivatives_of_a_shorter_audio_are_broken(fake_s3, media_service):
    fake_s3.put_wav(KEY, duration=95.0)
    fake_s3.put_derivatives(KEY, duration=120.0)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "broken"
    assert "waveform covers 120.0 s, the audio is 95.0 s" in result["problems"]
    assert "spectrogram covers" in result["problems"]


def test_gzip_spectrogram_is_broken(fake_s3, media_service):
    fake_s3.put_wav(KEY)
    fake_s3.put_derivatives(KEY)
    fake_s3.objects[(BUCKET, f"{DERIVATIVES}.spectrogram.bin")]["ContentEncoding"] = (
        "gzip"
    )

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "broken"
    assert "spectrogram is gzip-encoded" in result["problems"]


@pytest.mark.parametrize("name", ["spectrogram", "pitch"])
def test_header_that_does_not_match_the_size_is_broken(fake_s3, media_service, name):
    fake_s3.put_wav(KEY)
    fake_s3.put_derivatives(KEY)
    fake_s3.objects[(BUCKET, f"{DERIVATIVES}.{name}.bin")]["ContentLength"] += 100

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "broken"
    assert f"{name} header does not match the file size" in result["problems"]


def test_wav_with_a_large_metadata_chunk_before_the_audio(fake_s3, media_service):
    """A LIST chunk larger than the first read must not count as audio."""
    import struct

    byte_rate = 144000
    data_size = 3526656
    list_size = 98252
    header = (
        b"RIFF"
        + struct.pack("<I", 0)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 48000, byte_rate, 3, 24)
        + b"LIST"
        + struct.pack("<I", list_size)
        + b"\0" * list_size
        + b"data"
        + struct.pack("<I", data_size)
    )
    fake_s3.put(KEY, body=header, size=len(header) + data_size)
    fake_s3.put_derivatives(KEY, duration=data_size / byte_rate)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "works"
    assert result["audio_duration"] == pytest.approx(24.49, abs=0.01)


def test_peaks_without_duration_is_broken(fake_s3, media_service):
    fake_s3.put_wav(KEY)
    fake_s3.put_derivatives(KEY)
    fake_s3.put(f"{DERIVATIVES}.peaks.json", body=b'{"data":[0.1,0.2]}')

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "broken"
    assert "peaks file has no duration" in result["problems"]


def test_non_wav_audio_works_without_duration_check(fake_s3, media_service):
    key = content_key("a.mp3")
    fake_s3.put(key, body=b"ID3", size=5_000_000)
    fake_s3.put_derivatives(key)

    result = inspect_derivatives(media_service, BUCKET, key)

    assert result["status"] == "works"
    assert "duration not checked" in result["problems"]


def test_checks_read_only_small_ranges(fake_s3, media_service):
    fake_s3.put_wav(KEY, duration=3600.0)
    fake_s3.put_derivatives(KEY, duration=3600.0)
    ranges = []
    original = fake_s3.get_object

    def get_object(Bucket, Key, Range=None):
        ranges.append(Range)
        return original(Bucket=Bucket, Key=Key, Range=Range)

    fake_s3.get_object = get_object
    inspect_derivatives(media_service, BUCKET, KEY)

    assert ranges == ["bytes=0-4095", "bytes=-512", "bytes=0-5", "bytes=0-13"]


@pytest.mark.django_db
def test_record_check_creates_one_row_per_object(fake_s3, media_service):
    fake_s3.put_wav(KEY)

    record_check(BUCKET, KEY, media_service=media_service)
    record_check(BUCKET, KEY, media_service=media_service)

    row = MediaDerivativeStatus.objects.get()
    assert row.status == "missing"
    assert row.last_checked_at is not None


@pytest.mark.django_db
def test_failed_status_survives_a_check_until_derivatives_work(fake_s3, media_service):
    fake_s3.put(KEY)
    record_generation(
        BUCKET,
        KEY,
        {"success": False, "error": "audiowaveform error"},
        media_service=media_service,
    )

    row = record_check(BUCKET, KEY, media_service=media_service)
    assert row.status == "failed"
    assert row.last_error == "audiowaveform error"

    fake_s3.put_derivatives(KEY)
    row = record_check(BUCKET, KEY, media_service=media_service)
    assert row.status == "works"
    assert row.last_error == ""


@pytest.mark.django_db
def test_record_generation_success_reads_derivatives(fake_s3, media_service):
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY)

    row = record_generation(BUCKET, KEY, {"success": True}, media_service=media_service)

    assert row.status == "works"
    assert row.format_version is not None


@pytest.mark.django_db
def test_record_generation_maps_missing_source(media_service):
    row = record_generation(
        BUCKET,
        KEY,
        {"success": False, "error": f"Source file not found: {KEY}"},
        media_service=media_service,
    )

    assert row.status == "source_missing"


@pytest.mark.django_db
def test_record_generation_never_raises(media_service, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(
        "lacos.storage.services.media_derivative_recorder._get_row",
        broken,
    )

    assert (
        record_generation(BUCKET, KEY, {"success": False}, media_service=media_service)
        is None
    )


@pytest.mark.django_db
def test_collection_for_object_follows_the_resource_location():
    from django.contrib.contenttypes.models import ContentType

    collection = make_collection()
    bundle = make_bundle(collection)
    audio = add_audio(bundle, "a.wav")
    S3ResourceLocation.objects.create(
        s3_bucket=BUCKET,
        s3_key=KEY,
        content_type=ContentType.objects.get_for_model(audio),
        object_id=str(audio.id),
    )

    assert collection_for_object(BUCKET, KEY) == collection
    assert collection_for_object(BUCKET, "other.wav") is None
