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


def test_inspect_reports_current_when_all_derivatives_match(fake_s3, media_service):
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "current"
    assert result["source_etag"] == "abc"
    assert result["peaks_last_modified"] is not None


def test_inspect_accepts_missing_pitch(fake_s3, media_service):
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY, pitch=False)

    result = inspect_derivatives(media_service, BUCKET, KEY)

    assert result["status"] == "current"
    assert result["pitch_last_modified"] is None


def test_inspect_reports_missing_without_spectrogram(fake_s3, media_service):
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY)
    del fake_s3.objects[(BUCKET, "col/bundle/derivatives/a.wav.spectrogram.bin")]

    assert inspect_derivatives(media_service, BUCKET, KEY)["status"] == "missing"


@pytest.mark.parametrize("kwargs", [{"source_etag": "old"}, {"version": 1}])
def test_inspect_reports_stale(fake_s3, media_service, kwargs):
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY, **kwargs)

    assert inspect_derivatives(media_service, BUCKET, KEY)["status"] == "stale"


def test_inspect_reports_source_missing(media_service):
    assert inspect_derivatives(media_service, BUCKET, KEY)["status"] == "source_missing"


@pytest.mark.django_db
def test_record_check_creates_one_row_per_object(fake_s3, media_service):
    fake_s3.put(KEY)

    record_check(BUCKET, KEY, media_service=media_service)
    record_check(BUCKET, KEY, media_service=media_service)

    row = MediaDerivativeStatus.objects.get()
    assert row.status == "missing"
    assert row.last_checked_at is not None


@pytest.mark.django_db
def test_failed_status_survives_a_check_until_derivatives_are_current(
    fake_s3, media_service
):
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
    assert row.status == "current"
    assert row.last_error == ""


@pytest.mark.django_db
def test_record_generation_success_reads_derivatives(fake_s3, media_service):
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY)

    row = record_generation(BUCKET, KEY, {"success": True}, media_service=media_service)

    assert row.status == "current"
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
