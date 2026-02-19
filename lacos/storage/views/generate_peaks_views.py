"""Views for triggering audio waveform peaks generation from the dashboard."""

import logging

from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from lacos.explorer.media_utils import determine_media_type
from lacos.storage.media_tasks import generate_peaks_task
from lacos.storage.permissions import archivist_required, ArchivistRequiredMixin
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


@archivist_required
def generate_peaks_modal(request, bucket_name, folder_path=""):
    """Render the peaks generation modal content."""
    return render(request, "storage/generate_peaks_modal.html", {
        "bucket_name": bucket_name,
        "folder_path": folder_path,
    })


class GeneratePeaksView(ArchivistRequiredMixin, View):
    """Scan a bucket/folder for audio files and enqueue peaks generation."""

    def post(self, request, bucket_name, folder_path=""):
        bucket_service = BucketService()
        media_service = MediaProcessingService(bucket_service)
        paginator = bucket_service.s3_client.get_paginator("list_objects_v2")

        page_kwargs = {"Bucket": bucket_name}
        prefix = folder_path
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        if prefix:
            page_kwargs["Prefix"] = prefix

        enqueued = 0
        skipped = 0

        for page in paginator.paginate(**page_kwargs):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".peaks.json"):
                    continue
                if determine_media_type(None, key) != "audio":
                    continue
                if media_service.peaks_exist(bucket_name, key):
                    skipped += 1
                    continue
                generate_peaks_task(bucket_name, key)
                enqueued += 1

        if enqueued == 0 and skipped == 0:
            msg = "No audio files found."
            alert = "alert-warning"
        elif enqueued == 0:
            msg = f"All {skipped} audio files already have peaks."
            alert = "alert-info"
        else:
            msg = f"Enqueued {enqueued} peaks tasks."
            if skipped:
                msg += f" {skipped} already had peaks (skipped)."
            alert = "alert-success"

        html = (
            f'<div class="alert {alert} text-sm">'
            f"<span>{msg}</span>"
            f"</div>"
        )

        return HttpResponse(
            html,
            headers={"HX-Trigger": "peaksGenerationStarted"},
        )
