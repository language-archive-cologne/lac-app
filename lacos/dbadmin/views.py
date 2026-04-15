import json
import logging
from dataclasses import dataclass

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from lacos.blam.services.cleanup_service import CleanupService
from lacos.dbadmin.services import DatabaseStatsService
from lacos.blam.tasks import (
    backup_database_task,
    decompress_spectrograms_task,
    generate_all_peaks_task,
    reindex_collections_task,
    reindex_search_vectors_task,
)
from lacos.storage.derivative_audit_tasks import audit_derivatives_task
from lacos.users.tasks import index_edugain_idps
from lacos.storage.models import BackgroundTask
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class DashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "dbadmin/dashboard.html"

    def get_context_data(self, **kwargs):
        from lacos.blam.models.collection.collection_repository import Collection

        context = super().get_context_data(**kwargs)
        context["title"] = "Database Dashboard"
        context["pg_stats"] = DatabaseStatsService.get_pg_stats()
        context["backup_summary"] = DatabaseStatsService.get_backup_summary()
        context["active_tasks"] = BackgroundTask.objects.filter(
            status__in=[BackgroundTask.Status.QUEUED, BackgroundTask.Status.RUNNING]
        ).order_by("-created_at")[:10]
        context["metadata_stats"] = CleanupService.get_database_statistics()
        context["collection_buckets"] = sorted(
            b for b in Collection.objects.values_list("import_bucket", flat=True).distinct() if b
        )
        context["derivative_stats"] = self._get_derivative_stats()
        context["derivative_collections"] = self._get_derivative_collections()
        return context

    @staticmethod
    def _get_derivative_stats() -> dict:
        from lacos.storage.models import DerivativeStatus

        qs = DerivativeStatus.objects.all()
        total = qs.count()
        if total == 0:
            return {
                "total": 0,
                "with_peaks": 0,
                "with_spectrogram": 0,
                "with_pitch": 0,
                "complete": 0,
                "missing_all": 0,
                "last_audit": None,
            }
        return {
            "total": total,
            "with_peaks": qs.filter(peaks_exists=True).count(),
            "with_spectrogram": qs.filter(spectrogram_exists=True).count(),
            "with_pitch": qs.filter(pitch_exists=True).count(),
            "complete": qs.filter(
                peaks_exists=True, spectrogram_exists=True, pitch_exists=True
            ).count(),
            "missing_all": qs.filter(
                peaks_exists=False, spectrogram_exists=False, pitch_exists=False
            ).count(),
            "last_audit": qs.order_by("-last_checked_at").values_list(
                "last_checked_at", flat=True
            ).first(),
        }

    @staticmethod
    def _get_derivative_collections() -> list:
        from django.db.models import Count, Q, Value, CharField
        from django.db.models.functions import Substr, StrIndex

        from lacos.blam.models.collection.collection_repository import Collection
        from lacos.storage.models import DerivativeStatus

        if not DerivativeStatus.objects.exists():
            return []

        # Extract collection identifier = first path segment of source_s3_key
        rows = (
            DerivativeStatus.objects
            .annotate(
                collection_id=Substr(
                    "source_s3_key", 1,
                    StrIndex("source_s3_key", Value("/")) - 1,
                    output_field=CharField(),
                )
            )
            .values("collection_id")
            .annotate(
                total=Count("id"),
                with_peaks=Count("id", filter=Q(peaks_exists=True)),
                with_spectrogram=Count("id", filter=Q(spectrogram_exists=True)),
                with_pitch=Count("id", filter=Q(pitch_exists=True)),
                complete=Count("id", filter=Q(
                    peaks_exists=True, spectrogram_exists=True, pitch_exists=True,
                )),
                missing_all=Count("id", filter=Q(
                    peaks_exists=False, spectrogram_exists=False, pitch_exists=False,
                )),
            )
            .order_by("collection_id")
        )

        # Build display name lookup
        display_names = {}
        for col in Collection.objects.prefetch_related("header").all():
            header = col.header.first()
            if header and header.md_collection_display_name:
                display_names[col.identifier] = header.md_collection_display_name

        result = []
        for row in rows:
            cid = row["collection_id"]
            row["display_name"] = display_names.get(cid, "")
            row["pct_complete"] = round(100 * row["complete"] / row["total"]) if row["total"] else 0
            result.append(row)

        return result


class DerivativeBundlesView(SuperuserRequiredMixin, View):
    """HTMX partial: per-bundle derivative breakdown for a collection."""

    def get(self, request, collection_id: str):
        from django.db.models import Count, Q, Value, CharField
        from django.db.models.functions import Substr, StrIndex

        from lacos.storage.models import DerivativeStatus

        prefix = f"{collection_id}/"
        qs = DerivativeStatus.objects.filter(source_s3_key__startswith=prefix)

        # Extract bundle id = second path segment
        # source_s3_key minus the collection prefix, then take up to the next "/"
        rows = (
            qs.annotate(
                _remainder=Substr(
                    "source_s3_key",
                    len(prefix) + 1,
                    output_field=CharField(),
                ),
            )
            .annotate(
                bundle_id=Substr(
                    "_remainder", 1,
                    StrIndex("_remainder", Value("/")) - 1,
                    output_field=CharField(),
                ),
            )
            .values("bundle_id")
            .annotate(
                total=Count("id"),
                with_peaks=Count("id", filter=Q(peaks_exists=True)),
                with_spectrogram=Count("id", filter=Q(spectrogram_exists=True)),
                with_pitch=Count("id", filter=Q(pitch_exists=True)),
                complete=Count("id", filter=Q(
                    peaks_exists=True, spectrogram_exists=True, pitch_exists=True,
                )),
                missing_all=Count("id", filter=Q(
                    peaks_exists=False, spectrogram_exists=False, pitch_exists=False,
                )),
            )
            .order_by("bundle_id")
        )

        bundles = []
        for row in rows:
            row["pct_complete"] = round(100 * row["complete"] / row["total"]) if row["total"] else 0
            bundles.append(row)

        html = render_to_string(
            "dbadmin/partials/derivative_bundles.html",
            {"bundles": bundles, "collection_id": collection_id},
            request=request,
        )
        return HttpResponse(html)


# ---------------------------------------------------------------------------
# Background task enqueue / status views
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskAction:
    task_name: str
    description: str
    start_message: str
    callable_name: str
    extra_fields: tuple[str, ...] = ()


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
    "decompress-spectrograms": TaskAction(
        task_name="decompress_spectrograms",
        description="Decompress gzip-encoded spectrogram files for range-request support",
        start_message="Spectrogram decompression queued.",
        callable_name="decompress_spectrograms_task",
        extra_fields=("bucket_name",),
    ),
    "index-edugain": TaskAction(
        task_name="index_edugain_idps",
        description="Fetch eduGAIN metadata and index IdPs for discovery",
        start_message="eduGAIN IdP indexing queued.",
        callable_name="index_edugain_idps",
    ),
    "audit-derivatives": TaskAction(
        task_name="audit_derivatives",
        description="Audit derivative status for audio files in lacos-production",
        start_message="Derivative audit queued.",
        callable_name="audit_derivatives_task",
    ),
}

_TASK_CALLABLES = {
    "reindex_search_vectors_task": reindex_search_vectors_task,
    "backup_database_task": backup_database_task,
    "reindex_collections_task": reindex_collections_task,
    "generate_all_peaks_task": generate_all_peaks_task,
    "decompress_spectrograms_task": decompress_spectrograms_task,
    "index_edugain_idps": index_edugain_idps,
    "audit_derivatives_task": audit_derivatives_task,
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
            extra_kwargs = {
                field: request.POST[field]
                for field in task_action.extra_fields
                if request.POST.get(field)
            }

            def _enqueue_after_commit():
                try:
                    result = enqueue_callable(tracking_id=str(task_record.id), **extra_kwargs)
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


class TaskCancelView(SuperuserRequiredMixin, View):
    def post(self, request, task_id, *args, **kwargs):
        task = get_object_or_404(BackgroundTask, pk=task_id)
        try:
            BackgroundTaskService.cancel(task)
        except ValueError as exc:
            return HttpResponse(str(exc), status=400)
        task.refresh_from_db()
        return HttpResponse(
            render_to_string(
                "dbadmin/partials/task_status.html",
                {"task": task},
                request=request,
            )
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


# ---------------------------------------------------------------------------
# Database management views (cleanup / delete)
# ---------------------------------------------------------------------------


class DatabaseCleanupView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        results = CleanupService.run_full_cleanup()
        bundle_results = results["bundle_resources"]
        link_results = results["collection_bundle_links"]
        fixed_resources = bundle_results.get("fixed_resources", 0)
        fixed_links = link_results.get("fixed_links", 0)
        message = (
            f"Database cleanup completed. Fixed {fixed_resources} bundle resources "
            f"and {fixed_links} collection-bundle links."
        )
        errors = bundle_results.get("errors", []) + link_results.get("errors", [])
        if errors:
            message += f" Encountered {len(errors)} errors during cleanup."
        html = render_to_string(
            "dbadmin/partials/cleanup_results.html",
            {
                "message": message,
                "bundle_results": bundle_results,
                "link_results": link_results,
                "errors": errors,
            },
        )
        return HttpResponse(html)


class DatabaseDeleteAllView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        stats = CleanupService.get_database_statistics()
        html = render_to_string(
            "dbadmin/partials/confirm_delete_all.html",
            {
                "stats": stats,
                "action_url": reverse_lazy("dbadmin:delete_all_confirm"),
            },
        )
        return HttpResponse(html)


class DatabaseDeleteConfirmView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if "confirm" not in request.POST or not request.POST.get("confirm"):
            html = render_to_string(
                "dbadmin/partials/delete_results.html",
                {
                    "message": "Deletion not confirmed. Please check the confirmation checkbox.",
                    "operation": "all",
                    "errors": ["Confirmation checkbox not checked"],
                },
            )
            return HttpResponse(html)
        results = CleanupService.delete_all_data()
        deleted = results["deleted"]
        message = (
            f"Database reset completed. Deleted {deleted['collections']} collections, "
            f"{deleted['bundles']} bundles, and "
            f"{deleted['media_resources'] + deleted['written_resources'] + deleted['other_resources']} resources."
        )
        errors = results.get("errors", [])
        if errors:
            message += f" Encountered {len(errors)} errors during deletion."
        html = render_to_string(
            "dbadmin/partials/delete_results.html",
            {
                "message": message,
                "deleted": deleted,
                "errors": errors,
                "operation": "all",
            },
        )
        return HttpResponse(html)


class DatabaseDeleteCollectionsView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        stats = CleanupService.get_database_statistics()
        html = render_to_string(
            "dbadmin/partials/confirm_delete_collections.html",
            {
                "stats": stats,
                "action_url": reverse_lazy("dbadmin:delete_collections_confirm"),
            },
        )
        return HttpResponse(html)


class DatabaseDeleteCollectionsConfirmView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        results = CleanupService.delete_collections_only()
        deleted = results["deleted"]
        orphaned = results["orphaned"]
        message = (
            f"Collections deletion completed. Deleted {deleted['collections']} collections "
            f"and orphaned {orphaned['bundles']} bundles."
        )
        errors = results.get("errors", [])
        if errors:
            message += f" Encountered {len(errors)} errors during deletion."
        html = render_to_string(
            "dbadmin/partials/delete_results.html",
            {
                "message": message,
                "deleted": deleted,
                "orphaned": orphaned,
                "errors": errors,
                "operation": "collections",
            },
        )
        return HttpResponse(html)


class DatabaseDeleteBundlesView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        stats = CleanupService.get_database_statistics()
        html = render_to_string(
            "dbadmin/partials/confirm_delete_bundles.html",
            {
                "stats": stats,
                "action_url": reverse_lazy("dbadmin:delete_bundles_confirm"),
            },
        )
        return HttpResponse(html)


class DatabaseDeleteBundlesConfirmView(SuperuserRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        results = CleanupService.delete_bundles_only()
        deleted = results["deleted"]
        affected = results["affected"]
        message = (
            f"Bundles deletion completed. Deleted {deleted['bundles']} bundles and "
            f"{deleted['media_resources'] + deleted['written_resources'] + deleted['other_resources']} resources. "
            f"Affected {affected['collections']} collections."
        )
        errors = results.get("errors", [])
        if errors:
            message += f" Encountered {len(errors)} errors during deletion."
        html = render_to_string(
            "dbadmin/partials/delete_results.html",
            {
                "message": message,
                "deleted": deleted,
                "affected": affected,
                "errors": errors,
                "operation": "bundles",
            },
        )
        return HttpResponse(html)


class ScheduledTasksView(SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        periodic_summary = DatabaseStatsService.get_periodic_tasks_summary()
        recent_runs = (
            BackgroundTask.objects.filter(
                metadata__trigger="periodic",
            )
            .order_by("-created_at")[:20]
        )
        html = render_to_string(
            "dbadmin/partials/scheduled_tasks.html",
            {
                "periodic_tasks": periodic_summary,
                "recent_runs": recent_runs,
            },
            request=request,
        )
        return HttpResponse(html)


# ---------------------------------------------------------------------------
# Overview stats / Task history (HTMX partials)
# ---------------------------------------------------------------------------


class OverviewStatsView(SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        pg_stats = DatabaseStatsService.get_pg_stats()
        table_sizes = DatabaseStatsService.get_table_sizes()
        health_warnings = DatabaseStatsService.get_health_warnings()
        backup_summary = DatabaseStatsService.get_backup_summary()
        html = render_to_string(
            "dbadmin/partials/overview_stats.html",
            {
                "pg_stats": pg_stats,
                "table_sizes": table_sizes,
                "health_warnings": health_warnings,
                "backup_summary": backup_summary,
            },
            request=request,
        )
        return HttpResponse(html)


class TaskHistoryView(SuperuserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        qs = BackgroundTask.objects.all().order_by("-created_at")
        status_filter = request.GET.get("status", "")
        if status_filter:
            qs = qs.filter(status=status_filter)
        type_filter = request.GET.get("type", "")
        if type_filter:
            qs = qs.filter(task_name=type_filter)
        paginator = Paginator(qs, 20)
        page = paginator.get_page(request.GET.get("page", 1))
        task_names = (
            BackgroundTask.objects.values_list("task_name", flat=True)
            .distinct()
            .order_by("task_name")
        )
        html = render_to_string(
            "dbadmin/partials/task_history.html",
            {
                "tasks": page,
                "page_obj": page,
                "status_filter": status_filter,
                "type_filter": type_filter,
                "task_names": list(task_names),
                "status_choices": BackgroundTask.Status.choices,
            },
            request=request,
        )
        return HttpResponse(html)
