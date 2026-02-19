"""Views for triggering audio waveform peaks generation from the dashboard."""

import json
import logging

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views import View

from lacos.storage.media_tasks import scan_and_generate_peaks_task
from lacos.storage.permissions import archivist_required, ArchivistRequiredMixin
from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@archivist_required
def generate_peaks_modal(request, bucket_name, folder_path=""):
    """Render the peaks generation modal content."""
    return render(request, "storage/generate_peaks_modal.html", {
        "bucket_name": bucket_name,
        "folder_path": folder_path,
    })


class GeneratePeaksView(ArchivistRequiredMixin, View):
    """Enqueue a background scan for audio files and peaks generation."""

    def post(self, request, bucket_name, folder_path=""):
        try:
            bucket_service = BucketService()
            if not bucket_service.ensure_bucket_exists(bucket_name):
                return HttpResponse(
                    '<div class="alert alert-error text-sm">'
                    f"<span>Bucket '{bucket_name}' not found.</span></div>",
                    headers={"HX-Trigger": "peaksGenerationStarted"},
                )

            scope = folder_path or bucket_name
            task_record = BackgroundTaskService.create(
                task_name="generate_peaks",
                description=f"Generate peaks for {scope}",
                metadata={
                    "bucket_name": bucket_name,
                    "folder_path": folder_path,
                },
            )

            task_result = scan_and_generate_peaks_task(
                bucket_name=bucket_name,
                folder_path=folder_path,
                tracking_id=str(task_record.id),
            )

            task_id = getattr(task_result, "id", None)
            if task_id:
                BackgroundTaskService.attach_huey_id(task_record, task_id)

            status_html = render_to_string(
                "storage/background_task_status.html",
                {"task": task_record},
                request=request,
            )

            return HttpResponse(
                status_html,
                headers={"HX-Trigger": "peaksGenerationStarted"},
            )

        except Exception as exc:
            logger.error("Error triggering peaks generation: %s", exc)
            return HttpResponse(
                '<div class="alert alert-error text-sm">'
                f"<span>Error starting peaks generation: {exc}</span></div>",
                headers={"HX-Trigger": "peaksGenerationStarted"},
            )
