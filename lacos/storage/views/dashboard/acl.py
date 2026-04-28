"""
ACL admin dashboard views.

Handles ACL configuration, sync operations, and permission management.
"""
import json
import logging
import re
from types import SimpleNamespace
from urllib.parse import quote_plus

from django.conf import settings
from lacos.storage.permissions import archivist_required
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.models.acl_config import ACLConfig
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.constants import ACL_LEVEL_PUBLIC, ACL_LEVEL_ACADEMIC, ACL_LEVEL_RESTRICTED
from lacos.storage.services.acl_bulk_loader import (
    ACL_COLLECTION_BUNDLE_LOAD_MODE_ALL,
    ACL_COLLECTION_BUNDLE_LOAD_MODE_MISSING,
    VALID_COLLECTION_BUNDLE_LOAD_MODES,
    get_collection_bundle_queryset,
)
from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.tasks import load_collection_bundles_task
from lacos.storage.utils.acl import normalize_agent_uri
from lacos.users.utils import ensure_acl_agent_uri, generate_acl_agent_uri

logger = logging.getLogger(__name__)


def _redirect_with_message(target_url: str | None, message: str):
    destination = target_url or reverse("storage:acl_admin_dashboard")
    separator = "&" if "?" in destination else "?"
    return redirect(f"{destination}{separator}message={quote_plus(message)}")


def _resolve_acl_display_name(obj):
    """Resolve a display name for an ACL object."""
    if obj is None:
        return None
    candidate = getattr(obj, "name", None) or getattr(obj, "title", None)
    if not candidate and hasattr(obj, "get_general_info"):
        general_info = obj.get_general_info
        if general_info:
            candidate = getattr(general_info, "display_title", None) or getattr(general_info, "title", None)
    if not candidate:
        candidate = getattr(obj, "identifier", None)
    return candidate or str(getattr(obj, "pk", ""))


def _get_acl_queryset(model):
    """Get appropriate queryset for ACL model."""
    if model is Collection:
        return model.objects.all().prefetch_related("general_info")
    if model is Bundle:
        return model.objects.all().prefetch_related(
            "general_info",
            "structural_info__is_member_of_collection",
            "structural_info__is_member_of_collection__general_info",
        )
    return model.objects.all()


def _get_acl_options(model):
    """Get ACL options for a model."""
    options = []
    queryset = _get_acl_queryset(model).order_by("identifier")
    for obj in queryset:
        display_name = _resolve_acl_display_name(obj)
        identifier = getattr(obj, "identifier", str(obj.pk))
        options.append(
            {
                "id": str(obj.pk),
                "identifier": identifier,
                "name": display_name,
                "label": f"{identifier}{f' — {display_name}' if display_name else ''}",
            }
        )
    return options


def _render_load_summary_partial(request, summary=None, error_message=None):
    """Render load summary partial template."""
    html = render_to_string(
        "dashboard/partials/acl_load_summary.html",
        {"load_summary": summary, "error_message": error_message},
        request=request,
    )
    return HttpResponse(html)


# Route alias for legacy callers
_render_sync_summary_partial = _render_load_summary_partial


def _get_collection_bundle_mode_label(mode: str) -> str:
    if mode == ACL_COLLECTION_BUNDLE_LOAD_MODE_ALL:
        return "Re-load all"
    return "Load missing"


def _render_acl_bulk_load_status_partial(request, task) -> HttpResponse:
    html = render_to_string(
        "dashboard/partials/acl_bulk_load_status.html",
        {"task": task},
        request=request,
    )
    return HttpResponse(html)


def _build_acl_table_context_from_post_state(request, scope: str) -> dict[str, object]:
    """Rebuild ACL records table context from HTMX form POST state."""
    from lacos.storage.views.dashboard_views import _build_acl_table_context

    table_query = QueryDict("", mutable=True)
    for field_name in ("sort", "dir", "page", "q", "status", "access"):
        field_value = request.POST.get(field_name)
        if field_value not in (None, ""):
            table_query[field_name] = field_value

    state_request = SimpleNamespace(GET=table_query)
    return _build_acl_table_context(state_request, scope)


def _render_acl_single_action_htmx_response(
    request,
    *,
    scope: str,
    message: str,
    success: bool,
) -> HttpResponse:
    """Return status text plus OOB table replacement for single ACL actions."""
    status_class = "text-success" if success else "text-error"
    status_html = f'<span class="text-xs {status_class}">{escape(message)}</span>'

    table_context = _build_acl_table_context_from_post_state(request, scope)
    table_context["hx_oob"] = True
    table_html = render_to_string(
        "dashboard/partials/acl_records_table_wrapper.html",
        table_context,
        request=request,
    )

    return HttpResponse(f"{status_html}{table_html}")


def _build_bundle_access_overview():
    """Summarize bundle access levels grouped by parent collection."""
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    access_by_bundle_id = {
        str(object_id): access_level
        for object_id, access_level in ACLPermissions.objects.filter(
            content_type=bundle_ct
        ).values_list("object_id", "access_level")
    }

    grouped: dict[str, dict[str, object]] = {}
    for bundle in _get_acl_queryset(Bundle).order_by("identifier"):
        structural_info = next(iter(bundle.structural_info.all()), None)
        collection = structural_info.is_member_of_collection if structural_info else None

        if collection is None:
            collection_id = "__unassigned__"
            collection_identifier = "Unassigned"
            collection_name = "No linked collection"
        else:
            collection_id = str(collection.pk)
            collection_identifier = getattr(collection, "identifier", str(collection.pk)) or str(collection.pk)
            collection_name = _resolve_acl_display_name(collection)

        row = grouped.setdefault(
            collection_id,
            {
                "collection_id": collection_id,
                "collection_identifier": collection_identifier,
                "collection_name": collection_name,
                "total_bundles": 0,
                "public_count": 0,
                "academic_count": 0,
                "restricted_count": 0,
                "missing_acl_count": 0,
            },
        )

        row["total_bundles"] += 1
        level = access_by_bundle_id.get(str(bundle.pk))
        if level == ACL_LEVEL_PUBLIC:
            row["public_count"] += 1
        elif level == ACL_LEVEL_ACADEMIC:
            row["academic_count"] += 1
        elif level == ACL_LEVEL_RESTRICTED:
            row["restricted_count"] += 1
        else:
            row["missing_acl_count"] += 1

    rows = sorted(
        grouped.values(),
        key=lambda row: (
            row["collection_id"] == "__unassigned__",
            str(row["collection_identifier"]).lower(),
        ),
    )
    totals = {
        "collections": len(rows),
        "bundles": sum(int(row["total_bundles"]) for row in rows),
        "public": sum(int(row["public_count"]) for row in rows),
        "academic": sum(int(row["academic_count"]) for row in rows),
        "restricted": sum(int(row["restricted_count"]) for row in rows),
        "missing_acl": sum(int(row["missing_acl_count"]) for row in rows),
    }
    return rows, totals


@archivist_required
def acl_admin_dashboard(request):
    """
    Render the ACL Admin Dashboard with current settings, summary stats,
    and recent permission records.
    """
    # Load configuration
    cfg = None
    try:
        cfg = ACLConfig.get_solo()
    except Exception:
        cfg = None

    acl_flags = {
        "ACL_ENFORCEMENT_ENABLED": (cfg.enforcement_enabled if cfg else getattr(settings, "ACL_ENFORCEMENT_ENABLED", True)),
        "ACL_LOG_ACCESS_ATTEMPTS": (cfg.log_access_attempts if cfg else getattr(settings, "ACL_LOG_ACCESS_ATTEMPTS", True)),
        "ACL_DEFAULT_DENY": (cfg.default_deny if cfg else getattr(settings, "ACL_DEFAULT_DENY", True)),
    }

    try:
        # Stats
        total = ACLPermissions.objects.count()
        by_level = (
            ACLPermissions.objects.values("access_level")
            .order_by()
            .annotate(count=models.Count("id"))
        )

        # Recent entries
        recent = ACLPermissions.objects.select_related("content_type").order_by("-last_synced")[:25]
    except Exception as e:
        logger.exception("Error preparing ACL dashboard: %s", e)
        total = 0
        by_level = []
        recent = []

    def build_acl_summary(model, perms_qs):
        """Build ACL summary for a model."""
        pk_field = model._meta.pk
        base_qs = _get_acl_queryset(model)

        total_objects = model.objects.count()
        sync_object_ids = [
            pk_field.to_python(obj_id) for obj_id in perms_qs.values_list("object_id", flat=True)
        ]
        distinct_synced = len({str(obj_id) for obj_id in sync_object_ids})

        unsynced_qs = base_qs.exclude(pk__in=sync_object_ids)
        unsynced_objects = unsynced_qs.count()
        unsynced_samples = [
            {
                "identifier": getattr(obj, "identifier", str(obj.pk)),
                "name": _resolve_acl_display_name(obj),
            }
            for obj in unsynced_qs.order_by("identifier")[:5]
        ]

        by_level_local = list(perms_qs.values("access_level").order_by().annotate(count=models.Count("id")))
        recent_perms = list(perms_qs.order_by("-last_synced")[:10])
        recent_ids = [pk_field.to_python(perm.object_id) for perm in recent_perms]
        recent_objects = {
            str(obj.pk): obj
            for obj in _get_acl_queryset(model).filter(pk__in=recent_ids)
        }

        recent_local = []
        for perm in recent_perms:
            obj = recent_objects.get(str(perm.object_id))
            recent_local.append(
                {
                    "identifier": getattr(obj, "identifier", perm.object_id) if obj else perm.object_id,
                    "name": _resolve_acl_display_name(obj) if obj else None,
                    "access_level": perm.access_level,
                    "last_synced": perm.last_synced,
                }
            )

        last_synced_at = perms_qs.aggregate(models.Max("last_synced"))["last_synced__max"]

        return {
            "records": perms_qs.count(),
            "synced_objects": distinct_synced,
            "unsynced_objects": unsynced_objects,
            "unsynced_samples": unsynced_samples,
            "total_objects": total_objects,
            "by_level": by_level_local,
            "recent": recent_local,
            "last_synced_at": last_synced_at,
        }

    # Build summaries
    collection_ct = ContentType.objects.get_for_model(Collection)
    bundle_ct = ContentType.objects.get_for_model(Bundle)

    collection_perms = ACLPermissions.objects.filter(content_type=collection_ct)
    bundle_perms = ACLPermissions.objects.filter(content_type=bundle_ct)

    collection_summary = build_acl_summary(Collection, collection_perms)
    bundle_summary = build_acl_summary(Bundle, bundle_perms)

    overall_summary = {
        "records": collection_summary["records"] + bundle_summary["records"],
        "synced_objects": collection_summary["synced_objects"] + bundle_summary["synced_objects"],
        "unsynced_objects": collection_summary["unsynced_objects"] + bundle_summary["unsynced_objects"],
        "total_objects": collection_summary["total_objects"] + bundle_summary["total_objects"],
    }
    bundle_access_overview, bundle_access_totals = _build_bundle_access_overview()

    collection_options = []
    bundle_options = []

    active_tab = request.GET.get("tab", "records")
    if active_tab not in {"dashboard", "records"}:
        active_tab = "dashboard"

    records_scope = request.GET.get("scope", "collection")
    records_context = None
    if active_tab == "records":
        try:
            from lacos.storage.views.dashboard_views import _build_acl_table_context
            records_context = _build_acl_table_context(request, records_scope)
        except ValueError:
            records_scope = "collection"
            records_context = _build_acl_table_context(request, records_scope)

    return render(
        request,
        "dashboard/acl_admin_dashboard.html",
        {
            "acl_flags": acl_flags,
            "total": total,
            "by_level": by_level,
            "recent": recent,
            "collection_summary": collection_summary,
            "bundle_summary": bundle_summary,
            "overall_summary": overall_summary,
            "bundle_access_overview": bundle_access_overview,
            "bundle_access_totals": bundle_access_totals,
            "sync_summary": None,
            "collection_options": collection_options,
            "bundle_options": bundle_options,
            "active_tab": active_tab,
            "records_scope": records_scope,
            "records_context": records_context,
            "message": request.GET.get("message"),
        },
    )


@archivist_required
@require_http_methods(["POST"])
def acl_load_all(request):
    """
    Load ACLs from S3 for Collections and Bundles.
    Returns a load summary for HTMX or redirects with a message.
    """
    from lacos.storage.services.acl_service import ACLService

    scope = request.POST.get("scope", "all")
    service = ACLService(skip_bucket_check=True)
    results = []
    scope_label = "Collections & Bundles"

    try:
        if scope == "all":
            results = service.load_all()
        elif scope == "collections":
            scope_label = "Collections"
            results = [service.load_collection(c) for c in Collection.objects.all()]
        elif scope == "bundles":
            scope_label = "Bundles"
            results = [service.load_bundle(b) for b in Bundle.objects.all()]
        else:
            return _render_load_summary_partial(request, error_message=f"Invalid scope: {scope}")

        # Compute summary
        total_loaded = sum(1 for r in results if r.success)
        total_errors = sum(1 for r in results if not r.success)

        summary = {
            "scope": scope_label,
            "loaded": total_loaded,
            "errors": total_errors,
            "total": len(results),
        }

        if request.headers.get("HX-Request"):
            response = _render_load_summary_partial(request, summary=summary)
            if total_loaded:
                response["HX-Trigger"] = json.dumps(
                    {"aclRecordsRefresh": {"scope": request.POST.get("scope")}}
                )
            return response
        else:
            msg = f"Loaded {total_loaded} ACLs for {scope_label}"
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={msg}")

    except Exception as e:
        logger.exception("Error in acl_load_all: %s", e)
        if request.headers.get("HX-Request"):
            return _render_load_summary_partial(request, error_message=str(e))
        else:
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Load failed: {e}")


@archivist_required
@require_http_methods(["POST"])
def acl_load_selected(request):
    """Load ACLs from S3 for selected collections and bundles."""
    from lacos.storage.services.acl_service import ACLService

    collection_ids = [cid for cid in request.POST.getlist("collection_ids") if cid]
    bundle_ids = [bid for bid in request.POST.getlist("bundle_ids") if bid]

    if not collection_ids and not bundle_ids:
        return _render_load_summary_partial(request, error_message="Select at least one collection or bundle.")

    service = ACLService(skip_bucket_check=True)
    results = []

    try:
        collections = list(Collection.objects.filter(pk__in=collection_ids))
        bundles = list(Bundle.objects.filter(pk__in=bundle_ids))

        if not collections and not bundles:
            return _render_load_summary_partial(request, error_message="No matching collections or bundles found.")

        for collection in collections:
            results.append(service.load_collection(collection))
        for bundle in bundles:
            results.append(service.load_bundle(bundle))

        total_loaded = sum(1 for r in results if r.success)
        total_errors = sum(1 for r in results if not r.success)

        scope_parts = []
        if collections:
            scope_parts.append(f"{len(collections)} collection(s)")
        if bundles:
            scope_parts.append(f"{len(bundles)} bundle(s)")
        scope_label = f"Selected {', '.join(scope_parts)}"

        summary = {
            "scope": scope_label,
            "loaded": total_loaded,
            "errors": total_errors,
            "total": len(results),
        }

        if request.headers.get("HX-Request"):
            response = _render_load_summary_partial(request, summary=summary)
            if total_loaded:
                response["HX-Trigger"] = json.dumps(
                    {"aclRecordsRefresh": {"scope": request.POST.get("scope")}}
                )
            return response

        msg = f"Loaded {total_loaded} ACLs for {scope_label}"
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={msg}")

    except Exception as e:
        logger.exception("Error in acl_load_selected: %s", e)
        if request.headers.get("HX-Request"):
            return _render_load_summary_partial(request, error_message=str(e))
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Load failed: {e}")


@archivist_required
@require_http_methods(["POST"])
def acl_load_collection_bundles(request, collection_id):
    """Enqueue bundle ACL loading for all bundles in one collection."""
    mode = request.POST.get("mode", ACL_COLLECTION_BUNDLE_LOAD_MODE_MISSING)
    if mode not in VALID_COLLECTION_BUNDLE_LOAD_MODES:
        return HttpResponse(f"Invalid mode: {escape(mode)}", status=400)

    collection = get_object_or_404(Collection, pk=collection_id)
    bundle_total = get_collection_bundle_queryset(collection, mode).count()

    if bundle_total == 0:
        message = "No bundle ACLs matched this action."
        if request.headers.get("HX-Request"):
            return HttpResponse(f'<span class="text-xs text-base-content/70">{escape(message)}</span>')
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={quote_plus(message)}")

    mode_label = _get_collection_bundle_mode_label(mode)
    task_record = BackgroundTaskService.create(
        task_name="acl_load_collection_bundles",
        description=f"{mode_label} bundle ACLs for {collection.identifier}",
        metadata={
            "collection_id": str(collection.pk),
            "collection_identifier": collection.identifier,
            "mode": mode,
            "mode_label": mode_label,
            "bundle_total": bundle_total,
            "status_template": "dashboard/partials/acl_bulk_load_status.html",
            "refresh_event": "aclRecordsRefresh",
            "refresh_payload": {"scope": "collection"},
        },
    )

    task_result = load_collection_bundles_task(
        collection_id=str(collection.pk),
        mode=mode,
        tracking_id=str(task_record.id),
    )
    task_id = getattr(task_result, "id", None)
    if task_id:
        BackgroundTaskService.attach_huey_id(task_record, task_id)
        task_record.metadata["task_id"] = task_id
        task_record.save(update_fields=["metadata", "updated_at"])

    if request.headers.get("HX-Request"):
        return _render_acl_bulk_load_status_partial(request, task_record)

    return redirect(
        f"{reverse('storage:acl_admin_dashboard')}?message="
        f"{quote_plus(f'{mode_label} queued for {collection.identifier}.')}"
    )


def _render_save_summary_partial(request, summary=None, error_message=None):
    """Render save summary partial template."""
    html = render_to_string(
        "dashboard/partials/acl_save_summary.html",
        {"save_summary": summary, "error_message": error_message},
        request=request,
    )
    return HttpResponse(html)


@archivist_required
@require_http_methods(["POST"])
def acl_save_all(request):
    """
    Save ACLs from DB to S3 for Collections and Bundles.
    Returns a save summary for HTMX or redirects with a message.
    """
    from lacos.storage.services.acl_service import ACLService
    from django.contrib.contenttypes.models import ContentType

    scope = request.POST.get("scope", "all")
    service = ACLService(skip_bucket_check=True)
    results = []
    scope_label = "Collections & Bundles"

    try:
        if scope == "all":
            scope_label = "Collections & Bundles"
            for collection in Collection.objects.all():
                results.append(service.save_collection(collection))
            for bundle in Bundle.objects.all():
                results.append(service.save_bundle(bundle))
        elif scope == "collections":
            scope_label = "Collections"
            results = [service.save_collection(c) for c in Collection.objects.all()]
        elif scope == "bundles":
            scope_label = "Bundles"
            results = [service.save_bundle(b) for b in Bundle.objects.all()]
        else:
            return _render_save_summary_partial(request, error_message=f"Invalid scope: {scope}")

        # Compute summary
        total_saved = sum(1 for r in results if r.success)
        total_errors = sum(1 for r in results if not r.success)

        summary = {
            "scope": scope_label,
            "saved": total_saved,
            "errors": total_errors,
            "total": len(results),
        }

        if request.headers.get("HX-Request"):
            return _render_save_summary_partial(request, summary=summary)
        else:
            msg = f"Saved {total_saved} ACLs for {scope_label}"
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={msg}")

    except Exception as e:
        logger.exception("Error in acl_save_all: %s", e)
        if request.headers.get("HX-Request"):
            return _render_save_summary_partial(request, error_message=str(e))
        else:
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Save failed: {e}")


@archivist_required
@require_http_methods(["POST"])
def acl_load_single(request, object_type, object_id):
    """Load ACL from S3 for a single collection or bundle."""
    from lacos.storage.services.acl_service import ACLService

    if object_type not in {"collection", "bundle"}:
        return HttpResponse("Invalid object type", status=400)

    model = Collection if object_type == "collection" else Bundle
    service = ACLService(skip_bucket_check=True)

    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return HttpResponse("Object not found", status=404)

    try:
        if object_type == "collection":
            result = service.load_collection(obj, force_refresh=True)
        else:
            result = service.load_bundle(obj, force_refresh=True)

        if result.success:
            message = f"Loaded ACL for {object_type}"
        else:
            message = f"Failed to load: {result.error}"

        if request.headers.get("HX-Request"):
            return _render_acl_single_action_htmx_response(
                request,
                scope=object_type,
                message=message,
                success=result.success,
            )
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={message}")

    except Exception as e:
        logger.exception("Error in acl_load_single: %s", e)
        if request.headers.get("HX-Request"):
            return HttpResponse(f'<span class="text-xs text-error">Error: {e}</span>')
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Load failed: {e}")


@archivist_required
@require_http_methods(["POST"])
def acl_save_single(request, object_type, object_id):
    """Save ACL to S3 for a single collection or bundle."""
    from lacos.storage.services.acl_service import ACLService

    if object_type not in {"collection", "bundle"}:
        return HttpResponse("Invalid object type", status=400)

    model = Collection if object_type == "collection" else Bundle
    service = ACLService(skip_bucket_check=True)

    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return HttpResponse("Object not found", status=404)

    try:
        if object_type == "collection":
            result = service.save_collection(obj)
        else:
            result = service.save_bundle(obj)

        if result.success:
            message = f"Saved ACL for {object_type}"
        else:
            message = f"Failed to save: {result.error}"

        if request.headers.get("HX-Request"):
            return _render_acl_single_action_htmx_response(
                request,
                scope=object_type,
                message=message,
                success=result.success,
            )
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={message}")

    except Exception as e:
        logger.exception("Error in acl_save_single: %s", e)
        if request.headers.get("HX-Request"):
            return HttpResponse(f'<span class="text-xs text-error">Error: {e}</span>')
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Save failed: {e}")


@archivist_required
@require_http_methods(["POST"])
def acl_update_settings(request):
    """Update ACL configuration settings."""
    try:
        cfg = ACLConfig.get_solo()
        cfg.enforcement_enabled = request.POST.get("enforcement_enabled") == "on"
        cfg.log_access_attempts = request.POST.get("log_access_attempts") == "on"
        cfg.default_deny = request.POST.get("default_deny") == "on"
        cfg.save()

        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Settings updated")
    except Exception as e:
        logger.exception("Error updating ACL settings: %s", e)
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Update failed: {e}")


@archivist_required
@require_http_methods(["POST"])
def acl_sync_scope_fields(request):
    """Sync ACL for specific Collections or Bundles by ID."""
    from lacos.storage.services.acl_sync_service import ACLSyncService

    scope_type = request.POST.get("scope_type")  # "collection" or "bundle"
    object_ids = request.POST.getlist("object_ids[]")

    if not scope_type or not object_ids:
        return _render_sync_summary_partial(request, error_message="Missing scope_type or object_ids")

    service = ACLSyncService(skip_bucket_check=True)
    results = []

    try:
        for obj_id in object_ids:
            if scope_type == "collection":
                result = service.sync_collection_by_id(obj_id)
            elif scope_type == "bundle":
                result = service.sync_bundle_by_id(obj_id)
            else:
                continue
            results.append(result)

        total_synced = sum(r.get("synced", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)

        summary = {
            "scope": f"{len(object_ids)} {scope_type}(s)",
            "synced": total_synced,
            "errors": total_errors,
            "results": results,
        }

        return _render_sync_summary_partial(request, summary=summary)

    except Exception as e:
        logger.exception("Error in acl_sync_scope_fields: %s", e)
        return _render_sync_summary_partial(request, error_message=str(e))


@archivist_required
@require_http_methods(["POST"])
def acl_update_permission(request):
    """Allow administrators to manually adjust an object's recorded ACL level and agents."""
    from lacos.users.models import User, GroupACL

    access_level = request.POST.get("access_level")
    object_type = request.POST.get("object_type")
    object_id = request.POST.get("object_id")
    permission_id = request.POST.get("permission_id")
    next_url = request.POST.get("next")

    valid_levels = {choice[0] for choice in ACLPermissions.ACCESS_LEVEL_CHOICES}
    if not access_level or access_level not in valid_levels:
        return _redirect_with_message(next_url, "Invalid access level selected.")

    if object_type not in {"collection", "bundle"}:
        return _redirect_with_message(next_url, "Unknown ACL object type.")

    if not object_id:
        return _redirect_with_message(next_url, "Missing object identifier.")

    model = Collection if object_type == "collection" else Bundle

    obj = None
    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        obj = None

    expected_ct = ContentType.objects.get_for_model(model)

    perm = None
    if permission_id:
        perm = ACLPermissions.objects.filter(pk=permission_id).first()
        if perm is None:
            return _redirect_with_message(next_url, "ACL record could not be found.")
        if perm.content_type_id != expected_ct.id:
            return _redirect_with_message(next_url, "ACL record does not match the selected object.")
        if obj and str(perm.object_id) != str(obj.pk):
            return _redirect_with_message(next_url, "ACL record does not match the selected object.")
    else:
        if obj is None:
            return _redirect_with_message(next_url, "Cannot create ACL record for a missing object.")
        perm, _ = ACLPermissions.objects.get_or_create(
            content_type=expected_ct,
            object_id=str(obj.pk),
            defaults={
                "ACL_file_bucket": getattr(obj, "import_bucket", None),
                "ACL_file_key": getattr(obj, "import_object_key", None),
            },
        )

    # Build permissions_data based on access level and selected users/groups
    permissions_data = []
    read_agents = []

    if access_level == ACL_LEVEL_PUBLIC:
        permissions_data = [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}]
        read_agents = ["foaf:Agent"]
    elif access_level == ACL_LEVEL_ACADEMIC:
        permissions_data = [{"agentClass": "acl:AuthenticatedAgent", "mode": ["acl:Read"]}]
        read_agents = ["acl:AuthenticatedAgent"]
    elif access_level == ACL_LEVEL_RESTRICTED:
        user_ids = request.POST.getlist("user_ids")
        group_ids = request.POST.getlist("group_ids")
        extra_user_agents_raw = request.POST.get("extra_user_agents", "")
        extra_group_agents_raw = request.POST.get("extra_group_agents", "")

        def _parse_agent_list(raw_value: str) -> list[str]:
            if not raw_value:
                return []
            items: list[str] = []
            normalized = re.sub(r"\\+n", "\n", raw_value)
            for line in normalized.splitlines():
                parts = [part.strip() for part in line.split(",") if part.strip()]
                items.extend(parts)
            return [value for value in items if value]

        person_agents: set[str] = set()
        group_agents: set[str] = set()

        for user_id in user_ids:
            try:
                user = User.objects.get(pk=user_id)
                ensure_acl_agent_uri(user, save=True)
                if user.acl_agent_uri:
                    person_agents.add(user.acl_agent_uri)
            except User.DoesNotExist:
                pass

        for group_id in group_ids:
            try:
                group_acl = GroupACL.objects.get(pk=group_id)
                if group_acl.acl_agent_uri:
                    group_agents.add(group_acl.acl_agent_uri)
            except GroupACL.DoesNotExist:
                pass

        for agent in _parse_agent_list(extra_user_agents_raw):
            normalized = normalize_agent_uri(agent)
            if normalized:
                person_agents.add(normalized)

        for agent in _parse_agent_list(extra_group_agents_raw):
            normalized = normalize_agent_uri(agent)
            if normalized:
                group_agents.add(normalized)

        for agent in sorted(person_agents):
            permissions_data.append({
                "agentClass": "foaf:Person",
                "agent": agent,
                "mode": ["acl:Read"]
            })
            read_agents.append(agent)

        for agent in sorted(group_agents):
            permissions_data.append({
                "agentClass": "foaf:Group",
                "agent": agent,
                "mode": ["acl:Read"]
            })
            read_agents.append(agent)

    # Update the DB record
    perm.access_level = access_level
    perm.permissions_data = permissions_data if permissions_data else None
    perm.read_agents = read_agents if read_agents else None
    perm.last_synced = timezone.now()
    perm.save(update_fields=["access_level", "permissions_data", "read_agents", "last_synced"])

    # Save to S3
    from lacos.storage.services.acl_service import ACLService
    acl_service = ACLService(skip_bucket_check=True)
    save_result = acl_service.save_permission(perm)

    label = dict(ACLPermissions.ACCESS_LEVEL_CHOICES).get(access_level, access_level)
    identifier = object_id
    if obj is not None:
        identifier = getattr(obj, "identifier", str(obj.pk)) or str(obj.pk)

    if save_result.success:
        message = f"Saved {object_type} {identifier} as {label}"
    else:
        message = f"Updated DB but failed to save to S3: {save_result.error}"

    # Handle HTMX partial return
    if request.POST.get("return_partial") == "true" and request.headers.get("HX-Request"):
        return redirect(reverse("storage:acl_records_table", args=[object_type]))

    return _redirect_with_message(next_url, message)


@archivist_required
def acl_edit_permission_form(request, object_type, object_id):
    """Render the ACL edit form for a specific object."""
    from lacos.users.models import User, GroupACL

    if object_type not in {"collection", "bundle"}:
        return HttpResponse("Invalid object type", status=400)

    model = Collection if object_type == "collection" else Bundle

    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return HttpResponse("Object not found", status=404)

    ct = ContentType.objects.get_for_model(model)
    perm = ACLPermissions.objects.filter(content_type=ct, object_id=object_id).first()

    available_users = list(User.objects.order_by("username"))
    for user in available_users:
        user.effective_acl_agent_uri = user.acl_agent_uri or generate_acl_agent_uri(user)
    user_by_effective_agent = {
        user.effective_acl_agent_uri: user
        for user in available_users
        if getattr(user, "effective_acl_agent_uri", None)
    }

    # Get current read agents from permissions_data
    selected_user_ids = set()
    selected_group_ids = set()
    external_user_agents = set()
    external_group_agents = set()
    def _normalize_agent_values(values: set[str]) -> list[str]:
        flattened: list[str] = []
        for value in values:
            if not value:
                continue
            text = re.sub(r"\\+n", "\n", str(value))
            for line in text.splitlines():
                for part in line.split(","):
                    candidate = part.strip()
                    if candidate:
                        flattened.append(candidate)
        # Preserve order while deduplicating
        return list(dict.fromkeys(flattened))

    if perm and perm.permissions_data:
        for rule in perm.permissions_data:
            agent = rule.get("agent", "")
            agent_class = rule.get("agentClass", "")
            normalized_agent = normalize_agent_uri(agent)
            if agent_class == "foaf:Person" and agent:
                user = user_by_effective_agent.get(normalized_agent)
                if user:
                    selected_user_ids.add(user.id)
                else:
                    external_user_agents.add(agent)
            elif agent_class == "foaf:Group" and agent:
                group_acl = GroupACL.objects.filter(acl_agent_uri=agent).first()
                if group_acl:
                    selected_group_ids.add(group_acl.id)
                else:
                    external_group_agents.add(agent)
            elif agent:
                user = user_by_effective_agent.get(normalized_agent)
                if user:
                    selected_user_ids.add(user.id)
                    continue
                group_acl = GroupACL.objects.filter(acl_agent_uri=normalized_agent).first()
                if group_acl:
                    selected_group_ids.add(group_acl.id)
                else:
                    external_user_agents.add(agent)
    if perm and perm.read_agents:
        skip_agents = {"foaf:Agent", "acl:AuthenticatedAgent", "foaf:Person", "foaf:Group"}
        for agent in perm.read_agents:
            if not agent or agent in skip_agents:
                continue
            if normalize_agent_uri(agent) in user_by_effective_agent:
                continue
            if GroupACL.objects.filter(acl_agent_uri=agent).exists():
                continue
            if str(agent).startswith("urn:lacos:group:"):
                external_group_agents.add(agent)
            else:
                external_user_agents.add(agent)

    external_user_agents = set(_normalize_agent_values(external_user_agents))
    external_group_agents = set(_normalize_agent_values(external_group_agents))

    current_access_level = perm.access_level if perm else ACL_LEVEL_RESTRICTED
    if current_access_level not in {ACL_LEVEL_PUBLIC, ACL_LEVEL_ACADEMIC, ACL_LEVEL_RESTRICTED}:
        current_access_level = ACL_LEVEL_RESTRICTED

    context = {
        "object_type": object_type,
        "object_id": object_id,
        "permission_id": perm.pk if perm else None,
        "identifier": getattr(obj, "identifier", str(obj.pk)),
        "name": _resolve_acl_display_name(obj),
        "current_access_level": current_access_level,
        "access_level_choices": ACLPermissions.ACCESS_LEVEL_CHOICES,
        "available_users": available_users,
        "available_groups": GroupACL.objects.exclude(acl_agent_uri__isnull=True).exclude(acl_agent_uri="").select_related("group").order_by("group__name"),
        "selected_user_ids": selected_user_ids,
        "selected_group_ids": selected_group_ids,
        "external_user_agents": "\n".join(sorted(external_user_agents)),
        "external_group_agents": "\n".join(sorted(external_group_agents)),
        "next_url": request.GET.get("next", reverse("storage:acl_records_table", args=[object_type])),
    }

    return render(request, "dashboard/partials/acl_edit_form.html", context)
