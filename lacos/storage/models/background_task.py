import uuid

from django.db import models


class BackgroundTask(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    huey_task_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
