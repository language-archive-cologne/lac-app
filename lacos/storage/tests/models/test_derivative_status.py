import pytest
from django.db import IntegrityError
from django.utils import timezone

from lacos.storage.models import DerivativeStatus


@pytest.mark.django_db
def test_create_derivative_status():
    now = timezone.now()
    ds = DerivativeStatus.objects.create(
        bucket_name="lacos-production",
        source_s3_key="col/bundle/v1/content/audio.wav",
        source_etag="abc123",
        peaks_exists=True,
        spectrogram_exists=True,
        pitch_exists=False,
        last_checked_at=now,
    )
    ds.refresh_from_db()
    assert ds.bucket_name == "lacos-production"
    assert ds.peaks_exists is True
    assert ds.spectrogram_exists is True
    assert ds.pitch_exists is False
    assert ds.all_derivatives_exist is False
    assert ds.has_any_derivative is True


@pytest.mark.django_db
def test_unique_constraint_bucket_and_key():
    now = timezone.now()
    DerivativeStatus.objects.create(
        bucket_name="lacos-production",
        source_s3_key="audio.wav",
        last_checked_at=now,
    )
    with pytest.raises(IntegrityError):
        DerivativeStatus.objects.create(
            bucket_name="lacos-production",
            source_s3_key="audio.wav",
            last_checked_at=now,
        )


@pytest.mark.django_db
def test_defaults_false():
    now = timezone.now()
    ds = DerivativeStatus.objects.create(
        bucket_name="b",
        source_s3_key="k",
        last_checked_at=now,
    )
    assert ds.peaks_exists is False
    assert ds.spectrogram_exists is False
    assert ds.pitch_exists is False
    assert ds.all_derivatives_exist is False
    assert ds.has_any_derivative is False


@pytest.mark.django_db
def test_str_representation():
    now = timezone.now()
    ds = DerivativeStatus(
        bucket_name="b",
        source_s3_key="audio.wav",
        peaks_exists=True,
        last_checked_at=now,
    )
    assert "peaks" in str(ds)
    assert "spectrogram" not in str(ds)

    ds2 = DerivativeStatus(
        bucket_name="b",
        source_s3_key="audio.wav",
        last_checked_at=now,
    )
    assert "none" in str(ds2)
