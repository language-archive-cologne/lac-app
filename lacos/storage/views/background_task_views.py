import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from lacos.storage.models import BackgroundTask
from lacos.storage.permissions import archivist_required


def _get_status_template(task: BackgroundTask) -> str:
    return task.metadata.get("status_template") or "storage/background_task_status.html"


def _build_hx_trigger(task: BackgroundTask) -> dict[str, object]:
    payload: dict[str, object] = {}

    if task.status == BackgroundTask.Status.SUCCESS:
        message = task.message or "Task completed successfully."
        level = "success"
        if task.task_name == "acl_load_collection_bundles" and (task.result or {}).get("errors"):
            level = "error"
        payload["showMessage"] = {"message": message, "level": level}

        refresh_event = task.metadata.get("refresh_event")
        if refresh_event:
            payload[refresh_event] = task.metadata.get("refresh_payload") or {}

    elif task.status == BackgroundTask.Status.FAILED:
        message = task.error or "Background task failed."
        payload["showMessage"] = {"message": message, "level": "error"}

    return payload


@archivist_required
@require_GET
def background_task_status(request, task_id):
    task = get_object_or_404(BackgroundTask, pk=task_id)
    response = render(request, _get_status_template(task), {"task": task})

    trigger_payload = _build_hx_trigger(task)
    if trigger_payload:
        response["HX-Trigger"] = json.dumps(trigger_payload)

    return response
