import json
import logging
from dataclasses import dataclass

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from lacos.blam.tasks import (
    backup_database_task,
    generate_all_peaks_task,
    reindex_collections_task,
    reindex_search_vectors_task,
)
from lacos.storage.models import BackgroundTask
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class DashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "dbadmin/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Database Dashboard"
        return context


# ---------------------------------------------------------------------------
# Background task enqueue / status views
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskAction:
    task_name: str
    description: str
    start_message: str
    callable_name: str


TASK_ACTIONS = {
    "reindex": TaskAction(
        task_name="blam_reindex_search_vectors",
        description="Rebuild BLAM search vectors",
        start_message="Search reindex queued.",
        callable_name="reindex_search_vectors_task",
    ),
    "backup": TaskAction(
        task_name="blam_database_backup",
        description="Create DB backup and upload to S3",
        start_message="Database backup queued.",
        callable_name="backup_database_task",
    ),
    "reindex-collections": TaskAction(
        task_name="blam_reindex_collections",
        description="Reindex all collections and bundles from S3 XML",
        start_message="Collection reindex queued.",
        callable_name="reindex_collections_task",
    ),
    "generate-peaks": TaskAction(
        task_name="generate_audio_sidecars",
        description="Generate audio sidecars for all collections",
        start_message="Audio sidecar generation queued.",
        callable_name="generate_all_peaks_task",
    ),
}

_TASK_CALLABLES = {
    "reindex_search_vectors_task": reindex_search_vectors_task,
    "backup_database_task": backup_database_task,
    "reindex_collections_task": reindex_collections_task,
    "generate_all_peaks_task": generate_all_peaks_task,
}


class TaskEnqueueView(SuperuserRequiredMixin, View):
    def post(self, request, action: str, *args, **kwargs):
        task_action = TASK_ACTIONS.get(action)
        if task_action is None:
            return HttpResponse("Unknown task action.", status=400)

        task_record = BackgroundTaskService.create(
            task_name=task_action.task_name,
            description=task_action.description,
            metadata={"source": "dbadmin", "action": action},
        )

        try:
            enqueue_callable = _TASK_CALLABLES[task_action.callable_name]

            def _enqueue_after_commit():
                try:
                    result = enqueue_callable(tracking_id=str(task_record.id))
                    huey_task_id = getattr(result, "id", None)
                    if huey_task_id:
                        task = BackgroundTask.objects.filter(pk=task_record.id).first()
                        if not task:
                            return
                        metadata = task.metadata.copy() if task.metadata else {}
                        metadata["task_id"] = str(huey_task_id)
                        task.metadata = metadata
                        task.save(update_fields=["metadata", "updated_at"])
                        BackgroundTaskService.attach_huey_id(task, huey_task_id)
                except Exception as exc:
                    logger.error(
                        "Failed to enqueue task %s: %s", action, exc, exc_info=True
                    )
                    BackgroundTaskService.mark_failed(
                        str(task_record.id),
                        error_message=str(exc),
                        result={"success": False, "error": str(exc)},
                    )

            transaction.on_commit(_enqueue_after_commit)

            status_html = render_to_string(
                "dbadmin/partials/task_status.html",
                {"task": task_record},
                request=request,
            )
            return HttpResponse(
                status_html,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "showMessage": {
                                "message": task_action.start_message,
                                "level": "info",
                            }
                        }
                    )
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to queue task %s: %s", action, exc, exc_info=True
            )
            BackgroundTaskService.mark_failed(
                task_record,
                error_message=str(exc),
                result={"success": False, "error": str(exc)},
            )
            return HttpResponse(
                render_to_string(
                    "dbadmin/partials/task_status.html",
                    {"task": task_record},
                    request=request,
                ),
                status=500,
            )


class TaskStatusView(SuperuserRequiredMixin, View):
    def get(self, request, task_id, *args, **kwargs):
        task = get_object_or_404(BackgroundTask, pk=task_id)
        response = HttpResponse(
            render_to_string(
                "dbadmin/partials/task_status.html",
                {"task": task},
                request=request,
            )
        )
        if task.status == BackgroundTask.Status.SUCCESS:
            msg = task.message or "Task completed successfully."
            response["HX-Trigger"] = json.dumps(
                {"showMessage": {"message": msg, "level": "success"}}
            )
        elif task.status == BackgroundTask.Status.FAILED:
            msg = task.error or "Task failed."
            response["HX-Trigger"] = json.dumps(
                {"showMessage": {"message": msg, "level": "error"}}
            )
        return response
