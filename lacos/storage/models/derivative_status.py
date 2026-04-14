from django.db import models

from lacos.blam.models.base_model import UUIDTimestampModel


class DerivativeStatus(UUIDTimestampModel):
    """Tracks whether S3 source files have generated derivatives (peaks, spectrogram, pitch)."""

    bucket_name = models.CharField(max_length=255)
    source_s3_key = models.CharField(max_length=1024)
    source_etag = models.CharField(max_length=255, blank=True)
    peaks_exists = models.BooleanField(default=False)
    spectrogram_exists = models.BooleanField(default=False)
    pitch_exists = models.BooleanField(default=False)
    last_checked_at = models.DateTimeField()

    class Meta:
        verbose_name = "Derivative Status"
        verbose_name_plural = "Derivative Statuses"
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_name", "source_s3_key"],
                name="unique_bucket_source_key",
            ),
        ]
        indexes = [
            models.Index(fields=["bucket_name", "peaks_exists"]),
        ]

    def __str__(self):
        flags = []
        if self.peaks_exists:
            flags.append("peaks")
        if self.spectrogram_exists:
            flags.append("spectrogram")
        if self.pitch_exists:
            flags.append("pitch")
        status = ", ".join(flags) if flags else "none"
        return f"{self.source_s3_key} [{status}]"

    @property
    def all_derivatives_exist(self) -> bool:
        return self.peaks_exists and self.spectrogram_exists and self.pitch_exists

    @property
    def has_any_derivative(self) -> bool:
        return self.peaks_exists or self.spectrogram_exists or self.pitch_exists
