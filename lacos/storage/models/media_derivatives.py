from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from lacos.blam.models.base_model import UUIDTimestampModel


class DerivativeStatus(models.TextChoices):
    WORKS = "works", "Works"
    BROKEN = "broken", "Broken"
    MISSING = "missing", "Missing"
    FAILED = "failed", "Generation failed"
    SOURCE_MISSING = "source_missing", "Audio file missing"


class ElanLinkStatus(models.TextChoices):
    REFERENCED_FOUND = "referenced_found", "Linked by ELAN reference"
    NAME_FALLBACK = "name_fallback", "Linked by file name"
    REFERENCED_MISSING = "referenced_missing", "Named audio not in bundle"
    NO_AUDIO = "no_audio", "No audio"
    AUDIO_NO_LOCATION = "audio_no_location", "Audio not in storage"
    ELAN_UNREADABLE = "elan_unreadable", "ELAN file unreadable"


class MediaDerivativeStatus(UUIDTimestampModel):
    """State of the derivatives (peaks, spectrogram, pitch) of one audio object."""

    bucket = models.CharField(max_length=255)
    s3_key = models.CharField(max_length=1024)
    collection = models.ForeignKey(
        "blam.Collection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_derivative_statuses",
    )
    status = models.CharField(
        max_length=20,
        choices=DerivativeStatus.choices,
        default=DerivativeStatus.MISSING,
    )
    source_etag = models.CharField(max_length=255, blank=True)
    format_version = models.PositiveSmallIntegerField(null=True, blank=True)
    peaks_last_modified = models.DateTimeField(null=True, blank=True)
    spectrogram_last_modified = models.DateTimeField(null=True, blank=True)
    pitch_last_modified = models.DateTimeField(null=True, blank=True)
    audio_duration = models.FloatField(null=True, blank=True)
    problems = models.TextField(
        blank=True,
        help_text="The checks that failed, and the checks that could not run.",
    )
    last_error = models.TextField(blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Media Derivative Status"
        verbose_name_plural = "Media Derivative Statuses"
        constraints = [
            models.UniqueConstraint(
                fields=["bucket", "s3_key"],
                name="uniq_media_derivative_object",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["collection", "status"]),
        ]

    def __str__(self):
        return f"{self.bucket}/{self.s3_key} ({self.status})"


class ElanMediaLink(UUIDTimestampModel):
    """The audio that the Explorer plays for one ELAN resource."""

    elan_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
    )
    elan_object_id = models.CharField(max_length=36)
    elan_resource = GenericForeignKey("elan_content_type", "elan_object_id")
    elan_file_name = models.CharField(max_length=255)
    bundle = models.ForeignKey(
        "blam.Bundle",
        on_delete=models.CASCADE,
        related_name="elan_media_links",
    )
    collection = models.ForeignKey(
        "blam.Collection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elan_media_links",
    )
    elan_bucket = models.CharField(max_length=255, blank=True)
    elan_s3_key = models.CharField(max_length=1024, blank=True)
    referenced_media = models.JSONField(default=list, blank=True)
    audio_file_name = models.CharField(max_length=255, blank=True)
    audio_bucket = models.CharField(max_length=255, blank=True)
    audio_s3_key = models.CharField(max_length=1024, blank=True)
    audio_derivative = models.ForeignKey(
        MediaDerivativeStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elan_links",
    )
    link_status = models.CharField(max_length=20, choices=ElanLinkStatus.choices)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "ELAN Media Link"
        verbose_name_plural = "ELAN Media Links"
        constraints = [
            models.UniqueConstraint(
                fields=["elan_content_type", "elan_object_id"],
                name="uniq_elan_media_link_resource",
            ),
        ]
        indexes = [
            models.Index(fields=["link_status"]),
            models.Index(fields=["collection", "link_status"]),
        ]

    def __str__(self):
        return f"{self.elan_file_name} ({self.link_status})"
