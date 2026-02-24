from django.db import models

from lacos.blam.models.base_model import UUIDTimestampModel


class BackgroundTask(UUIDTimestampModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    task_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    huey_task_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_running(self, message: str | None = None):
        self.status = self.Status.RUNNING
        if message is not None:
            self.message = message
        self.save(update_fields=["status", "message", "updated_at"])

    def mark_success(self, message: str | None = None, result: dict | None = None):
        self.status = self.Status.SUCCESS
        if message is not None:
            self.message = message
        if result is not None:
            self.result = result
        self.save(update_fields=["status", "message", "result", "updated_at"])

    def mark_failed(self, error_message: str, result: dict | None = None):
        self.status = self.Status.FAILED
        self.error = error_message
        if result is not None:
            self.result = result
        self.save(update_fields=["status", "error", "result", "updated_at"])

    def mark_cancelled(self, message: str | None = None):
        self.status = self.Status.CANCELLED
        if message is not None:
            self.message = message
        self.save(update_fields=["status", "message", "updated_at"])
