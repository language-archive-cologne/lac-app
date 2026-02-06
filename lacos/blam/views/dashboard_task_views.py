from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from lacos.blam.tasks import backup_database_task
from lacos.blam.tasks import reindex_collections_task
from lacos.blam.tasks import reindex_search_vectors_task
from lacos.storage.models import BackgroundTask
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DashboardTaskAction:
    task_name: str
    description: str
    start_message: str
    enqueue_name: str


class DashboardTaskPermissionsMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class DashboardTaskEnqueueView(DashboardTaskPermissionsMixin, View):
    ACTIONS = {
        "reindex": DashboardTaskAction(
            task_name="blam_reindex_search_vectors",
            description="Rebuild BLAM search vectors",
            start_message="Search reindex queued.",
            enqueue_name="reindex_search_vectors_task",
        ),
        "backup": DashboardTaskAction(
            task_name="blam_database_backup",
            description="Create DB backup and upload to S3",
            start_message="Database backup queued.",
            enqueue_name="backup_database_task",
        ),
        "reindex-collections": DashboardTaskAction(
            task_name="blam_reindex_collections",
            description="Reindex all collections and bundles from S3 XML",
            start_message="Collection reindex queued.",
            enqueue_name="reindex_collections_task",
        ),
    }

    def post(self, request, action: str, *args, **kwargs):
        task_action = self.ACTIONS.get(action)
        if task_action is None:
            return HttpResponse("Unknown dashboard task action.", status=400)

        task_record = BackgroundTaskService.create(
            task_name=task_action.task_name,
            description=task_action.description,
            metadata={"source": "blam_dashboard", "action": action},
        )

        try:
            enqueue_callable = globals()[task_action.enqueue_name]
            task_result = enqueue_callable(tracking_id=str(task_record.id))
            huey_task_id = getattr(task_result, "id", None)
            if huey_task_id:
                BackgroundTaskService.attach_huey_id(task_record, huey_task_id)
                task_record.metadata["task_id"] = str(huey_task_id)
                task_record.save(update_fields=["metadata", "updated_at"])

            status_html = render_to_string(
                "blam/dashboard/partials/task_status.html",
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
            logger.error("Failed to queue dashboard task %s: %s", action, exc, exc_info=True)
            BackgroundTaskService.mark_failed(
                task_record,
                error_message=str(exc),
                result={"success": False, "error": str(exc)},
            )
            error_html = render_to_string(
                "blam/dashboard/partials/task_status.html",
                {"task": task_record},
                request=request,
            )
            return HttpResponse(error_html, status=500)


class DashboardTaskStatusView(DashboardTaskPermissionsMixin, View):
    def get(self, request, task_id, *args, **kwargs):
        task = get_object_or_404(BackgroundTask, pk=task_id)
        response = HttpResponse(
            render_to_string(
                "blam/dashboard/partials/task_status.html",
                {"task": task},
                request=request,
            )
        )

        if task.status == BackgroundTask.Status.SUCCESS:
            message = task.message or "Task completed successfully."
            response["HX-Trigger"] = json.dumps({"showMessage": {"message": message, "level": "success"}})
        elif task.status == BackgroundTask.Status.FAILED:
            message = task.error or "Task failed."
            response["HX-Trigger"] = json.dumps({"showMessage": {"message": message, "level": "error"}})
        return response
