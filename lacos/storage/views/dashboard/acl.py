"""
ACL admin dashboard views.

Handles ACL configuration, sync operations, and permission management.
"""
import logging
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.models.acl_config import ACLConfig
from lacos.storage.models.acl_permissions import ACLPermissions

logger = logging.getLogger(__name__)


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
        return model.objects.all().prefetch_related("general_info", "structural_info__is_member_of_collection")
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


def _render_sync_summary_partial(request, summary=None, error_message=None):
    """Render sync summary partial template."""
    html = render_to_string(
        "dashboard/partials/acl_sync_summary.html",
        {"sync_summary": summary, "error_message": error_message},
        request=request,
    )
    return HttpResponse(html)


@login_required
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

    collection_options = _get_acl_options(Collection)
    bundle_options = _get_acl_options(Bundle)

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
            "sync_summary": None,
            "collection_options": collection_options,
            "bundle_options": bundle_options,
            "message": request.GET.get("message"),
        },
    )


@login_required
@require_http_methods(["POST"])
def acl_sync_all(request):
    """
    Trigger a full ACL sync for Collections and Bundles.
    Returns a sync summary for HTMX or redirects with a message.
    """
    from lacos.storage.services.acl_sync_service import ACLSyncService

    scope = request.POST.get("scope", "all")
    service = ACLSyncService(skip_bucket_check=True)
    results = []
    scope_label = "Collections & Bundles"

    try:
        if scope == "all":
            results = service.sync_all()
        elif scope == "collections":
            scope_label = "All Collections"
            results = [service.sync_collections()]
        elif scope == "bundles":
            scope_label = "All Bundles"
            results = [service.sync_bundles()]
        else:
            return _render_sync_summary_partial(request, error_message=f"Invalid scope: {scope}")

        # Flatten results and compute summary
        total_synced = sum(r.get("synced", 0) for r in results)
        total_created = sum(r.get("created", 0) for r in results)
        total_updated = sum(r.get("updated", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)

        summary = {
            "scope": scope_label,
            "synced": total_synced,
            "created": total_created,
            "updated": total_updated,
            "errors": total_errors,
            "results": results,
        }

        if request.headers.get("HX-Request"):
            return _render_sync_summary_partial(request, summary=summary)
        else:
            msg = f"Synced {total_synced} permissions for {scope_label}"
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={msg}")

    except Exception as e:
        logger.exception("Error in acl_sync_all: %s", e)
        if request.headers.get("HX-Request"):
            return _render_sync_summary_partial(request, error_message=str(e))
        else:
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Sync failed: {e}")


@login_required
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


@login_required
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
