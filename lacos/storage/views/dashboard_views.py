import ast
import json
import logging
from urllib.parse import quote_plus, urlencode

from django.conf import settings
from lacos.storage.permissions import archivist_required, manager_or_archivist_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import models
from django.db.models import CharField, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Cast
from django.http import HttpResponse, QueryDict
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from django.views.decorators.http import require_http_methods

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.common.mixins import BucketCoordinatorMixin, HtmxTemplateHelperMixin
from lacos.common.mixins.htmx_template_helpers import ROOT_FOLDER_SENTINEL
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.models.acl_config import ACLConfig
from lacos.storage.observability import profiling_scope
from lacos.storage.services.collection_service import BucketListingPage

logger = logging.getLogger(__name__)


def _resolve_acl_display_name(obj):
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


def _get_acl_options(model):
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


def _get_acl_queryset(model):
    if model is Collection:
        return model.objects.all().prefetch_related("general_info")
    if model is Bundle:
        return model.objects.all().prefetch_related("general_info", "structural_info__is_member_of_collection")
    return model.objects.all()


def _render_sync_summary_partial(request, summary=None, error_message=None):
    html = render_to_string(
        "dashboard/partials/acl_sync_summary.html",
        {"sync_summary": summary, "error_message": error_message},
        request=request,
    )
    return HttpResponse(html)



def _redirect_with_message(target_url: str | None, message: str):
    destination = target_url or reverse("storage:acl_admin_dashboard")
    separator = "&" if "?" in destination else "?"
    return redirect(f"{destination}{separator}message={quote_plus(message)}")


def _get_acl_scope_model(scope: str):
    if scope == "collection":
        return Collection
    if scope == "bundle":
        return Bundle
    raise ValueError(f"Unsupported ACL scope: {scope}")


def _build_acl_table_context(request, scope: str) -> dict[str, object]:
    model = _get_acl_scope_model(scope)
    content_type = ContentType.objects.get_for_model(model)

    search_term = (request.GET.get("q") or "").strip()
    status_filter = request.GET.get("status") or "all"
    access_filter = request.GET.get("access") or "all"

    existing_ids = model.objects.annotate(
        pk_str=Cast("pk", output_field=CharField())
    ).values("pk_str")

    total_objects = model.objects.count()
    has_acl_count = ACLPermissions.objects.filter(
        content_type=content_type,
        object_id__in=Subquery(existing_ids),
    ).count()
    missing_acl_count = max(total_objects - has_acl_count, 0)
    missing_object_count = ACLPermissions.objects.filter(
        content_type=content_type
    ).exclude(
        object_id__in=Subquery(existing_ids),
    ).count()
    orphan_count = missing_object_count
    total_count = total_objects + missing_object_count

    sort = request.GET.get("sort", "identifier")
    direction = request.GET.get("dir", "asc")
    valid_sorts = {"identifier", "access_level", "last_synced"}
    if sort not in valid_sorts:
        sort = "identifier"
    if direction not in {"asc", "desc"}:
        direction = "asc"

    page_size = getattr(settings, "STORAGE_ACL_TABLE_PAGE_SIZE", 25)
    page_number = request.GET.get("page") or 1

    if status_filter == "missing_object":
        orphans = ACLPermissions.objects.filter(
            content_type=content_type
        ).exclude(
            object_id__in=Subquery(existing_ids),
        )

        if search_term:
            orphans = orphans.filter(object_id__icontains=search_term)

        if access_filter != "all":
            orphans = orphans.filter(access_level=access_filter)

        if sort == "access_level":
            order_expr = (
                F("access_level").desc(nulls_last=True)
                if direction == "desc"
                else F("access_level").asc(nulls_last=True)
            )
        elif sort == "last_synced":
            order_expr = (
                F("last_synced").desc(nulls_last=True)
                if direction == "desc"
                else F("last_synced").asc(nulls_last=True)
            )
        else:
            order_expr = (
                F("object_id").desc(nulls_last=True)
                if direction == "desc"
                else F("object_id").asc(nulls_last=True)
            )

        orphans = orphans.order_by(order_expr)
        filtered_count = orphans.count()
        paginator = Paginator(orphans, page_size)
        page_obj = paginator.get_page(page_number)

        rows = [
            {
                "scope": scope,
                "object_id": perm.object_id,
                "identifier": perm.object_id,
                "name": None,
                "permission_id": perm.pk,
                "has_permission": True,
                "object_exists": False,
                "access_level": perm.access_level,
                "last_synced": perm.last_synced,
                "read_agents": perm.read_agents or [],
                "bucket": perm.ACL_file_bucket,
                "key": perm.ACL_file_key,
            }
            for perm in page_obj.object_list
        ]
        page_obj.object_list = rows
    else:
        base_qs = _get_acl_queryset(model).annotate(
            pk_str=Cast("pk", output_field=CharField())
        )

        perm_qs = ACLPermissions.objects.filter(
            content_type=content_type,
            object_id=OuterRef("pk_str"),
        )

        objects = base_qs.annotate(
            has_permission=Exists(perm_qs),
            access_level=Subquery(perm_qs.values("access_level")[:1]),
            last_synced=Subquery(perm_qs.values("last_synced")[:1]),
            read_agents=Subquery(perm_qs.values("read_agents")[:1]),
            bucket=Subquery(perm_qs.values("ACL_file_bucket")[:1]),
            key=Subquery(perm_qs.values("ACL_file_key")[:1]),
            permission_id=Subquery(perm_qs.values("id")[:1]),
        )

        if search_term:
            objects = objects.filter(
                Q(identifier__icontains=search_term)
                | Q(general_info__display_title__icontains=search_term)
                | Q(pk_str__icontains=search_term)
            ).distinct()

        if status_filter == "missing_acl":
            objects = objects.filter(has_permission=False)
        elif status_filter == "has_acl":
            objects = objects.filter(has_permission=True)

        if access_filter != "all":
            objects = objects.filter(access_level=access_filter)

        if sort == "access_level":
            order_expr = (
                F("access_level").desc(nulls_last=True)
                if direction == "desc"
                else F("access_level").asc(nulls_last=True)
            )
        elif sort == "last_synced":
            order_expr = (
                F("last_synced").desc(nulls_last=True)
                if direction == "desc"
                else F("last_synced").asc(nulls_last=True)
            )
        else:
            order_expr = (
                F("identifier").desc(nulls_last=True)
                if direction == "desc"
                else F("identifier").asc(nulls_last=True)
            )

        objects = objects.order_by(order_expr)
        filtered_count = objects.count()
        paginator = Paginator(objects, page_size)
        page_obj = paginator.get_page(page_number)

        rows = [
            {
                "scope": scope,
                "object_id": str(obj.pk),
                "identifier": getattr(obj, "identifier", str(obj.pk)),
                "name": _resolve_acl_display_name(obj),
                "permission_id": obj.permission_id,
                "has_permission": bool(obj.has_permission),
                "object_exists": True,
                "access_level": obj.access_level,
                "last_synced": obj.last_synced,
                "read_agents": obj.read_agents or [],
                "bucket": obj.bucket,
                "key": obj.key,
            }
            for obj in page_obj.object_list
        ]
        page_obj.object_list = rows

    base_url = reverse("storage:acl_admin_dashboard")
    filter_params = {}
    if search_term:
        filter_params["q"] = search_term
    if status_filter and status_filter != "all":
        filter_params["status"] = status_filter
    if access_filter and access_filter != "all":
        filter_params["access"] = access_filter

    filter_query = urlencode(filter_params)
    filter_suffix = f"&{filter_query}" if filter_query else ""

    next_url = (
        f"{base_url}?tab=records&scope={scope}&sort={sort}&dir={direction}&page={page_obj.number}{filter_suffix}"
    )

    sort_toggles = {}
    for field in ("identifier", "access_level", "last_synced"):
        if field == sort and direction == "asc":
            sort_toggles[field] = "desc"
        else:
            sort_toggles[field] = "asc"

    return {
        "scope": scope,
        "page_obj": page_obj,
        "orphan_count": orphan_count,
        "missing_acl_count": missing_acl_count,
        "missing_object_count": missing_object_count,
        "has_acl_count": has_acl_count,
        "total_count": total_count,
        "filtered_count": filtered_count,
        "search_term": search_term,
        "status_filter": status_filter,
        "access_filter": access_filter,
        "filter_query": filter_query,
        "sort": sort,
        "direction": direction,
        "available_sorts": [
            {"id": "identifier", "label": "Identifier"},
            {"id": "access_level", "label": "Access"},
            {"id": "last_synced", "label": "Last synced"},
        ],
        "endpoint": reverse("storage:acl_records_table", args=[scope]),
        "access_level_choices": ACLPermissions.ACCESS_LEVEL_CHOICES,
        "next_url": next_url,
        "page_size": page_size,
        "sort_toggles": sort_toggles,
    }


def _build_acl_overview_context():
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
        total = ACLPermissions.objects.count()
        by_level = (
            ACLPermissions.objects.values("access_level")
            .order_by()
            .annotate(count=models.Count("id"))
        )

        recent = ACLPermissions.objects.select_related("content_type").order_by("-last_synced")[:25]
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Error preparing ACL dashboard: %s", exc)
        total = 0
        by_level = []
        recent = []

    def build_acl_summary(model, perms_qs):
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

    collection_ct = ContentType.objects.get_for_model(Collection)
    bundle_ct = ContentType.objects.get_for_model(Bundle)

    collection_perms = ACLPermissions.objects.filter(content_type=collection_ct).select_related("content_type")
    bundle_perms = ACLPermissions.objects.filter(content_type=bundle_ct).select_related("content_type")

    collection_summary = build_acl_summary(Collection, collection_perms)
    bundle_summary = build_acl_summary(Bundle, bundle_perms)

    overall_summary = {
        "records": collection_summary["records"] + bundle_summary["records"],
        "synced_objects": collection_summary["synced_objects"] + bundle_summary["synced_objects"],
        "unsynced_objects": collection_summary["unsynced_objects"] + bundle_summary["unsynced_objects"],
        "total_objects": collection_summary["total_objects"] + bundle_summary["total_objects"],
    }

    return {
        "acl_flags": acl_flags,
        "total": total,
        "by_level": by_level,
        "recent": recent,
        "collection_summary": collection_summary,
        "bundle_summary": bundle_summary,
        "overall_summary": overall_summary,
        "collection_options": [],
        "bundle_options": [],
    }


@manager_or_archivist_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing all workspace buckets.
    Only loads root level items initially for better performance.
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "archivist_dashboard",
        request_id=request_id,
        metadata={
            "htmx": bool(request.headers.get("HX-Request")),
            "force_fresh": request.GET.get("force_fresh", "false").lower() == "true",
        },
    ) as session:
        bucket_service = BucketService(skip_bucket_check=True)
        bucket_state = BucketCoordinatorMixin()

        workspace_buckets = bucket_service.get_all_accessible_buckets()
        session.metadata["workspace_bucket_count"] = len(workspace_buckets)

        active_bucket = bucket_state.ensure_active_bucket(request, workspace_buckets)
        session.metadata["active_bucket"] = active_bucket

        auto_load_url = None
        if active_bucket:
            auto_load_url = reverse("storage:bucket_content_htmx", kwargs={"bucket_name": active_bucket})
            if request.GET.get("force_fresh", "false").lower() == "true":
                auto_load_url = f"{auto_load_url}?force_fresh=true"

        message = request.GET.get('message', None)

        return render(
            request,
            "dashboard/archivist_dashboard.html",
            {
                "workspace_buckets": workspace_buckets,
                "active_bucket": active_bucket,
                "ocfl_buckets": bucket_service.ocfl_buckets,
                "message": message,
                "auto_load_url": auto_load_url,
            },
        )


@archivist_required
def acl_admin_dashboard(request):
    """
    Render the ACL Admin Dashboard with current settings, summary stats,
    and recent permission records.
    """
    overview = _build_acl_overview_context()
    active_tab = request.GET.get("tab", "dashboard")
    if active_tab not in {"dashboard", "records"}:
        active_tab = "dashboard"

    scope = request.GET.get("scope", "collection")
    records_context = None
    if active_tab == "records":
        try:
            records_context = _build_acl_table_context(request, scope)
        except ValueError:
            scope = "collection"
            records_context = _build_acl_table_context(request, scope)

    context = {
        **overview,
        "sync_summary": None,
        "active_tab": active_tab,
        "records_context": records_context,
        "records_scope": scope,
        "message": request.GET.get("message"),
    }

    return render(
        request,
        "dashboard/acl_admin_dashboard.html",
        context,
    )


@archivist_required
@require_http_methods(["GET"])
def acl_dashboard_panel(request):
    """HTMX endpoint rendering the overview dashboard panel."""
    overview = _build_acl_overview_context()
    return render(
        request,
        "dashboard/partials/acl_dashboard_overview.html",
        {**overview, "sync_summary": None},
    )


@archivist_required
@require_http_methods(["GET"])
def acl_records_panel(request):
    scope = request.GET.get("scope", "collection")
    try:
        records_context = _build_acl_table_context(request, scope)
    except ValueError:
        records_context = _build_acl_table_context(request, "collection")
        scope = "collection"

    return render(
        request,
        "dashboard/partials/acl_records_panel.html",
        {
            "records_context": records_context,
            "records_scope": scope,
        },
    )


@archivist_required
@require_http_methods(["GET"])
def acl_records_table(request, scope: str):
    try:
        records_context = _build_acl_table_context(request, scope)
    except ValueError:
        return HttpResponse(status=400)
    return render(
        request,
        "dashboard/partials/acl_records_table_wrapper.html",
        records_context,
    )


@archivist_required
@require_http_methods(["POST"])
def acl_delete_orphans(request, scope: str):
    try:
        model = _get_acl_scope_model(scope)
    except ValueError:
        return HttpResponse(status=400)

    content_type = ContentType.objects.get_for_model(model)
    existing_ids = model.objects.annotate(
        pk_str=Cast("pk", output_field=CharField())
    ).values("pk_str")
    orphans = ACLPermissions.objects.filter(content_type=content_type).exclude(
        object_id__in=Subquery(existing_ids)
    )
    deleted_count, _ = orphans.delete()

    if request.headers.get("HX-Request"):
        records_context = _build_acl_table_context(request, scope)
        response = render(
            request,
            "dashboard/partials/acl_records_table_wrapper.html",
            records_context,
        )
        response["HX-Trigger"] = json.dumps(
            {"aclOrphansDeleted": {"scope": scope, "deleted": deleted_count}}
        )
        return response

    message = f"Deleted {deleted_count} orphaned ACL record(s) for {scope}s."
    return redirect(
        f"{reverse('storage:acl_admin_dashboard')}?tab=records&scope={scope}&message={quote_plus(message)}"
    )


@archivist_required
@require_http_methods(["POST"])
def acl_sync_all(request):
    """
    Trigger a full ACL sync for Collections and Bundles.
    Returns a small JSON summary for HTMX or redirects back with a message.
    """
    from lacos.storage.services.acl_sync_service import ACLSyncService

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
            results = [service.sync_collection(obj) for obj in Collection.objects.all()]
        elif scope == "bundles":
            scope_label = "All Bundles"
            bundle_qs = _get_acl_queryset(Bundle)
            results = [service.sync_bundle(obj) for obj in bundle_qs]
        elif scope == "collection":
            collection_id = request.POST.get("collection_id")
            if not collection_id:
                raise ValueError("Please select a collection to sync.")
            collection = _get_acl_queryset(Collection).filter(pk=collection_id).first()
            if not collection:
                raise ValueError("Collection not found.")
            scope_label = f"Collection {getattr(collection, 'identifier', collection_id)}"
            results = [service.sync_collection(collection)]
        elif scope == "bundle":
            bundle_id = request.POST.get("bundle_id")
            if not bundle_id:
                raise ValueError("Please select a bundle to sync.")
            bundle = _get_acl_queryset(Bundle).filter(pk=bundle_id).first()
            if not bundle:
                raise ValueError("Bundle not found.")
            scope_label = f"Bundle {getattr(bundle, 'identifier', bundle_id)}"
            results = [service.sync_bundle(bundle)]
        else:
            raise ValueError("Invalid sync scope.")
    except ValueError as exc:
        if request.headers.get("HX-Request"):
            return _render_sync_summary_partial(request, summary=None, error_message=str(exc))
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={quote_plus(str(exc))}")

    updated = sum(1 for r in results if r.updated)
    found = sum(1 for r in results if r.found)
    errors = [r for r in results if r.error]

    summary = {
        "total": len(results),
        "found": found,
        "updated": updated,
        "errors": len(errors),
        "missing": len(results) - found,
        "scope": scope,
        "scope_label": scope_label,
        "by_type": {
            "collections": sum(1 for r in results if r.object_type == "Collection"),
            "bundles": sum(1 for r in results if r.object_type == "Bundle"),
        },
    }

    # HTMX request -> return partial HTML
    if request.headers.get("HX-Request"):
        return _render_sync_summary_partial(request, summary=summary)

    # Regular POST -> redirect back to dashboard with message
    message = (
        f"{scope_label}: processed {summary['total']} objects — found {summary['found']}, "
        f"updated {summary['updated']}, errors {summary['errors']}"
    )
    return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={quote_plus(message)}")


@archivist_required
@require_http_methods(["POST"])
def acl_update_settings(request):
    """
    Update ACL settings via HTMX form.
    Returns the updated settings card HTML.
    """
    try:
        from lacos.storage.models.acl_config import ACLConfig

        cfg = ACLConfig.get_solo()
        enforcement_enabled = request.POST.get("enforcement_enabled") == "on"
        log_access_attempts = request.POST.get("log_access_attempts") == "on"
        default_deny = request.POST.get("default_deny") == "on"

        cfg.enforcement_enabled = enforcement_enabled
        cfg.log_access_attempts = log_access_attempts
        cfg.default_deny = default_deny
        cfg.save(update_fields=["enforcement_enabled", "log_access_attempts", "default_deny", "updated_at"])

        context = {
            "acl_flags": {
                "ACL_ENFORCEMENT_ENABLED": cfg.enforcement_enabled,
                "ACL_LOG_ACCESS_ATTEMPTS": cfg.log_access_attempts,
                "ACL_DEFAULT_DENY": cfg.default_deny,
            }
        }
        html = render_to_string("dashboard/partials/acl_settings_card.html", context, request=request)
        return HttpResponse(html)
    except Exception as e:
        logger.exception("Failed to update ACL settings: %s", e)
        return HttpResponse(f"Error updating settings: {e}", status=500)


@archivist_required
@require_http_methods(["GET"])
def acl_sync_scope_fields(request):
    scope = request.GET.get("scope", "all")
    context = {
        "scope": scope,
        "collection_options": _get_acl_options(Collection) if scope == "collection" else [],
        "bundle_options": _get_acl_options(Bundle) if scope == "bundle" else [],
    }
    return render(
        request,
        "dashboard/partials/acl_sync_scope_fields.html",
        context,
    )


@archivist_required
@require_http_methods(["POST"])
def acl_update_permission(request):
    """Allow administrators to manually adjust an object's recorded ACL level."""
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
    from lacos.users.models import User, GroupACL
    from lacos.storage.constants import ACL_LEVEL_PUBLIC, ACL_LEVEL_ACADEMIC, ACL_LEVEL_RESTRICTED

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

        for user_id in user_ids:
            try:
                user = User.objects.get(pk=user_id)
                if user.acl_agent_uri:
                    permissions_data.append({
                        "agentClass": "foaf:Person",
                        "agent": user.acl_agent_uri,
                        "mode": ["acl:Read"]
                    })
                    read_agents.append(user.acl_agent_uri)
            except User.DoesNotExist:
                pass

        for group_id in group_ids:
            try:
                group_acl = GroupACL.objects.get(pk=group_id)
                if group_acl.acl_agent_uri:
                    permissions_data.append({
                        "agentClass": "foaf:Group",
                        "agent": group_acl.acl_agent_uri,
                        "mode": ["acl:Read"]
                    })
                    read_agents.append(group_acl.acl_agent_uri)
            except GroupACL.DoesNotExist:
                pass
    # restricted = empty permissions

    # Update the record
    perm.access_level = access_level
    perm.permissions_data = permissions_data if permissions_data else None
    perm.read_agents = read_agents if read_agents else None
    perm.last_synced = timezone.now()
    perm.save(update_fields=["access_level", "permissions_data", "read_agents", "last_synced"])

    label = dict(ACLPermissions.ACCESS_LEVEL_CHOICES).get(access_level, access_level)
    identifier = object_id
    if obj is not None:
        identifier = getattr(obj, "identifier", str(obj.pk)) or str(obj.pk)
    # Handle HTMX partial return
    if request.POST.get("return_partial") == "true" and request.headers.get("HX-Request"):
        return _render_acl_records_table(request, object_type)

    return _redirect_with_message(
        next_url,
        f"Updated {object_type} {identifier} to {label}.",
    )


def _render_acl_records_table(request, scope):
    """Helper to re-render the ACL records table after an update."""
    from lacos.storage.views.dashboard.acl import _build_records_context
    context = _build_records_context(request, scope)
    return render(
        request,
        "dashboard/partials/acl_permissions_table.html",
        context,
    )


@archivist_required
def acl_edit_permission_form(request, object_type, object_id):
    """Render the ACL edit form for a specific object."""
    from lacos.users.models import User, GroupACL
    from lacos.storage.constants import ACL_LEVEL_ACADEMIC, ACL_LEVEL_PUBLIC, ACL_LEVEL_RESTRICTED

    if object_type not in {"collection", "bundle"}:
        return HttpResponse("Invalid object type", status=400)

    model = Collection if object_type == "collection" else Bundle

    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return HttpResponse("Object not found", status=404)

    ct = ContentType.objects.get_for_model(model)
    perm = ACLPermissions.objects.filter(content_type=ct, object_id=object_id).first()

    # Get current read agents from permissions_data
    selected_user_ids = set()
    selected_group_ids = set()
    if perm and perm.permissions_data:
        for rule in perm.permissions_data:
            agent = rule.get("agent", "")
            agent_class = rule.get("agentClass", "")
            if agent_class == "foaf:Person" and agent:
                # Find user with this URI
                user = User.objects.filter(acl_agent_uri=agent).first()
                if user:
                    selected_user_ids.add(user.id)
            elif agent_class == "foaf:Group" and agent:
                # Find group with this URI
                group_acl = GroupACL.objects.filter(acl_agent_uri=agent).first()
                if group_acl:
                    selected_group_ids.add(group_acl.id)

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
        "available_users": User.objects.exclude(acl_agent_uri__isnull=True).exclude(acl_agent_uri="").order_by("username"),
        "available_groups": GroupACL.objects.exclude(acl_agent_uri__isnull=True).exclude(acl_agent_uri="").select_related("group").order_by("group__name"),
        "selected_user_ids": selected_user_ids,
        "selected_group_ids": selected_group_ids,
        "next_url": request.GET.get("next", reverse("storage:acl_records_table", args=[object_type])),
    }

    return render(request, "dashboard/partials/acl_edit_form.html", context)


@manager_or_archivist_required
def load_folder_contents(request, bucket_type, folder_path):
    """
    Load contents of a specific folder when expanded.
    Now supports any workspace bucket, not just ingest/production.
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "load_folder_contents",
        request_id=request_id,
        metadata={
            "bucket_type": bucket_type,
            "folder_path": folder_path,
            "htmx": True,
        },
    ) as session:
        bucket_service = BucketService(skip_bucket_check=True)

        if bucket_type in bucket_service.get_all_accessible_buckets():
            bucket = bucket_type
        else:
            bucket = bucket_service.ingest_bucket if bucket_type == 'ingest' else bucket_service.production_bucket
        session.metadata["resolved_bucket"] = bucket

        sanitized_path = folder_path
        try:
            if sanitized_path == ROOT_FOLDER_SENTINEL:
                sanitized_path = ""
            sanitized_path = sanitized_path.replace('//', '/')
            logger.info("Loading folder contents for %s bucket, path: %s", bucket_type, sanitized_path or "/")
            force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
            session.metadata["force_fresh"] = force_fresh

            try:
                requested_max_keys = int(request.GET.get("max_keys", "") or 0)
            except ValueError:
                requested_max_keys = 0
            pagination_enabled = getattr(bucket_service, "dashboard_pagination_enabled", True)
            if requested_max_keys <= 0:
                requested_max_keys = bucket_service.dashboard_page_size if pagination_enabled else 0
            continuation_token = request.GET.get("continuation_token") or None
            session.metadata["continuation_token"] = continuation_token
            session.metadata["max_keys"] = requested_max_keys

            listing_page = bucket_service.get_folder_contents(
                bucket,
                sanitized_path,
                max_keys=requested_max_keys if pagination_enabled else None,
                continuation_token=continuation_token,
                force_fresh=force_fresh,
            )
            session.metadata["returned_item_count"] = len(listing_page)
            session.metadata["has_more"] = listing_page.has_more
            session.metadata["next_token"] = listing_page.next_token

            preview_names = ", ".join(item["name"] for item in listing_page[:5])
            more_indicator = "…" if len(listing_page) > 5 else ""
            logger.debug(
                "Loaded %s items for %s%s%s",
                len(listing_page),
                sanitized_path,
                f" — {preview_names}" if preview_names else "",
                more_indicator,
            )

        except Exception as e:
            logger.error(f"Error loading folder contents for {sanitized_path or ROOT_FOLDER_SENTINEL}: {str(e)}")
            session.metadata["error"] = str(e)
            listing_page = BucketListingPage(items=[], has_more=False, next_token=None, bucket=bucket, prefix=sanitized_path)
            requested_max_keys = locals().get("requested_max_keys", 0)
            continuation_token = locals().get("continuation_token", None)

        session.metadata["folder_path"] = sanitized_path
        return render(
            request,
            "dashboard/folder_contents_partial.html",
            {
                "listing": listing_page,
                "bucket_type": bucket_type,
                "folder_path": sanitized_path,
                "folder_path_param": sanitized_path or ROOT_FOLDER_SENTINEL,
                "is_root": sanitized_path in ("", None),
                "max_keys": requested_max_keys,
                "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
            },
        )


@manager_or_archivist_required
def bucket_size_info(request, bucket_name):
    """HTMX endpoint returning bucket size details."""
    bucket_service = BucketService(skip_bucket_check=True)
    accessible = set(bucket_service.get_all_accessible_buckets())

    if bucket_name not in accessible:
        return HttpResponse(status=404)

    force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
    size_result = bucket_service.get_bucket_total_size(bucket_name, force_fresh=force_fresh)

    context = {
        "bucket_name": bucket_name,
        "total_size": size_result.get("total_size", 0),
        "total_size_formatted": size_result.get("total_size_formatted", "0 B"),
        "object_count": size_result.get("object_count", 0),
        "success": size_result.get("success", False),
        "error": size_result.get("error"),
    }

    html = render_to_string("dashboard/partials/bucket_size_info.html", context, request=request)
    return HttpResponse(html)


@manager_or_archivist_required
def dashboard_content(request, bucket_type):
    """
    Return only the structure content for a specific bucket type.
    This is used for AJAX/HTMX refreshes of just one section of the dashboard.
    
    Args:
        bucket_type (str): Either "ingest" or "production"
        
    Returns:
        Rendered partial template with the requested bucket structure
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "dashboard_content",
        request_id=request_id,
        metadata={"bucket_type": bucket_type, "htmx": True},
    ) as session:
        try:
            bucket_service = BucketService(skip_bucket_check=True)
            force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
            session.metadata["force_fresh"] = force_fresh

            if bucket_type == "ingest":
                resolved_bucket = bucket_service.ingest_bucket
            elif bucket_type == "production":
                resolved_bucket = bucket_service.production_bucket
            else:
                return HttpResponse("Invalid bucket type", status=400)

            pagination_enabled = getattr(bucket_service, "dashboard_pagination_enabled", True)
            page_size = bucket_service.dashboard_page_size if pagination_enabled else None

            listing = bucket_service.get_folder_contents(
                resolved_bucket,
                "",
                max_keys=page_size if pagination_enabled else None,
                force_fresh=force_fresh,
            )

            session.metadata["resolved_bucket"] = resolved_bucket
            session.metadata["child_count"] = len(listing)
            session.metadata["has_more"] = listing.has_more
            session.metadata["next_token"] = listing.next_token

            logger.info(f"Refreshing {bucket_type} structure with {len(listing)} items (has_more={listing.has_more})")

            return render(
                request,
                "dashboard/folder_structure_partial.html",
                {
                    "listing": listing,
                    "bucket_type": bucket_type,
                    "page_size": page_size,
                }
            )
        except Exception as e:
            logger.exception(f"Error loading dashboard content for {bucket_type}: {str(e)}")
            session.metadata["error"] = str(e)
            return HttpResponse(f"Error: {str(e)}", status=500)


@method_decorator(archivist_required, name='dispatch')
class BucketContentHTMXView(HtmxTemplateHelperMixin, View):
    """
    Return bucket content for HTMX bucket switching.
    Returns the complete bucket content area.
    """

    def get(self, request, bucket_name):
        request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
        with profiling_scope(
            "bucket_content_htmx",
            request_id=request_id,
            metadata={"bucket": bucket_name, "htmx": True},
        ) as session:
            try:
                force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
                try:
                    requested_max_keys = int(request.GET.get("max_keys", "") or 0)
                except ValueError:
                    requested_max_keys = 0
                continuation_token = request.GET.get("continuation_token") or None

                session.metadata.update(
                    {
                        "force_fresh": force_fresh,
                        "continuation_token": continuation_token,
                        "max_keys": requested_max_keys,
                    }
                )

                prefetch_root = bool(continuation_token or requested_max_keys > 0)
                prefetch_param = request.GET.get("prefetch_root")
                if prefetch_param is not None:
                    prefetch_root = prefetch_param.lower() == "true"
                session.metadata["prefetch_root"] = prefetch_root

                content_html = self.render_bucket_content_template(
                    request,
                    bucket_name,
                    continuation_token=continuation_token,
                    max_keys=requested_max_keys if requested_max_keys > 0 else None,
                    force_fresh=force_fresh,
                    prefetch_root=prefetch_root,
                )
                selector_html = self.build_bucket_tabs_oob_response(
                    request=request,
                    active_bucket=bucket_name
                )
                session.metadata["rendered"] = True

                response_html = f'{content_html}{selector_html}'

                return HttpResponse(response_html)
            except Exception as e:
                logger.exception(f"Error loading bucket content for {bucket_name}: {str(e)}")
                session.metadata["error"] = str(e)
                return HttpResponse(f"Error: {str(e)}", status=500)


# Class-based view is now used directly in URLs


@archivist_required
def file_info_htmx(request, bucket_type, object_path):
    """Provide file metadata details via HTMX."""
    bucket_service = BucketService(skip_bucket_check=True)
    target_id = request.GET.get("target_id") or request.GET.get("targetId")

    if not target_id:
        target_id = slugify(f"file-info-{object_path}")

    if request.GET.get("clear"):
        html = render_to_string(
            "dashboard/partials/file_info_placeholder.html",
            {"target_id": target_id},
            request=request,
        )
        return HttpResponse(html)

    accessible_buckets = set(bucket_service.get_all_accessible_buckets())

    if bucket_type in accessible_buckets:
        bucket_name = bucket_type
    elif bucket_type == "ingest":
        bucket_name = bucket_service.ingest_bucket
    elif bucket_type == "production":
        bucket_name = bucket_service.production_bucket
    else:
        return HttpResponse(status=404)

    info_result = bucket_service.get_file_info(bucket_name, object_path)

    context = {
        "target_id": target_id,
        "bucket_type": bucket_type,
        "object_path": object_path,
        "file_name": info_result.get("file_name") or object_path.rstrip("/").split("/")[-1],
        "file_size_formatted": info_result.get("file_size_formatted"),
        "content_type": info_result.get("content_type"),
        "last_modified": info_result.get("last_modified"),
        "metadata": info_result.get("metadata", {}),
        "success": info_result.get("success", False),
        "error": info_result.get("error"),
    }

    html = render_to_string(
        "dashboard/partials/file_info_panel.html",
        context,
        request=request,
    )
    return HttpResponse(html)


@method_decorator(archivist_required, name='dispatch')
class BucketSelectHTMXView(HtmxTemplateHelperMixin, View):
    """Return updated bucket select dropdown for upload modal."""

    def get(self, request):
        """Render bucket select dropdown."""
        bucket_service = BucketService(skip_bucket_check=True)
        workspace_buckets = bucket_service.get_all_accessible_buckets()
        active_bucket = self.get_active_bucket(request)

        html = render_to_string(
            'dashboard/partials/bucket_select.html',
            {
                'workspace_buckets': workspace_buckets,
                'active_bucket': active_bucket,
                'oob': False,
            },
            request=request,
        )
        return HttpResponse(html)


@method_decorator(archivist_required, name='dispatch')
class CreateBucketHTMXView(HtmxTemplateHelperMixin, View):
    """
    Create a new bucket via HTMX form submission.
    Returns updated bucket selector tabs with OOB updates.
    """

    def post(self, request):
        try:
            from lacos.storage.services.bucket_service import BucketService

            # Get form data
            bucket_name = request.POST.get('bucketName', '').strip()
            enable_ocfl = request.POST.get('enableOCFL') == 'on'

            if not bucket_name:
                return HttpResponse("Bucket name is required", status=400)

            # Create the bucket using BucketService
            bucket_service = BucketService(skip_bucket_check=True)
            result = bucket_service.create_bucket(bucket_name, enable_ocfl)

            if not result["success"]:
                return HttpResponse(result["error"], status=400)

            logger.info(f"Successfully created bucket: {bucket_name}, OCFL: {enable_ocfl}")

            # Only update bucket tabs, keep current view active
            current_active_bucket = self.get_active_bucket(request)

            if not current_active_bucket:
                current_active_bucket = request.POST.get('currentActiveBucket')

            # If still not set (first bucket creation), use the new bucket
            if not current_active_bucket:
                current_active_bucket = bucket_name

            # Render bucket tabs directly (form targets #bucket-tabs with outerHTML swap)
            tabs_html = self.render_bucket_tabs_template(
                request=request,
                active_bucket=current_active_bucket,
                success_message=result["message"]
            )

            # Add trigger to close modal
            return self.add_htmx_trigger(tabs_html, {'closeModal': 'create-bucket-modal'})

        except Exception as e:
            logger.exception(f"Error creating bucket: {str(e)}")
            return HttpResponse(f"Error creating bucket: {str(e)}", status=500)


# Class-based view is now used directly in URLs


@archivist_required
@require_http_methods(["DELETE"])
def delete_bucket_htmx(request, bucket_name):
    """
    Delete a bucket via HTMX request.
    Returns updated bucket selector tabs.
    """
    try:
        bucket_service = BucketService(skip_bucket_check=True)

        # Verify bucket access
        if bucket_name not in bucket_service.get_all_accessible_buckets():
            return HttpResponse("Bucket not accessible", status=403)

        # Delete the bucket (this would need to be implemented in BucketService)
        logger.info(f"Deleting bucket: {bucket_name}")

        # Get updated bucket list
        workspace_buckets = bucket_service.get_all_accessible_buckets()
        ocfl_buckets = bucket_service.ocfl_buckets

        # Set first available bucket as active
        active_bucket = workspace_buckets[0] if workspace_buckets else None

        return render(
            request,
            "dashboard/bucket_tabs_partial.html",
            {
                "workspace_buckets": workspace_buckets,
                "ocfl_buckets": ocfl_buckets,
                "active_bucket": active_bucket,
                "success_message": f"Bucket '{bucket_name}' deleted successfully"
            }
        )
    except Exception as e:
        logger.exception(f"Error deleting bucket: {str(e)}")
        return HttpResponse(f"Error deleting bucket: {str(e)}", status=500)


@method_decorator(archivist_required, name='dispatch')
class RenameBucketModalHTMXView(HtmxTemplateHelperMixin, View):
    """Serve the bucket rename modal populated with current values."""

    def get(self, request, bucket_name):
        html = render_to_string(
            'dashboard/partials/rename_bucket_modal.html',
            {
                'modal_open': True,
                'form_action': reverse('storage:rename_bucket_htmx', args=[bucket_name]),
                'current_name': bucket_name,
                'new_name': bucket_name,
                'error': None,
                'oob': False,
                'csrf_token': get_token(request),
            },
            request=request,
        )
        return HttpResponse(html)


@method_decorator(archivist_required, name='dispatch')
class RenameObjectModalHTMXView(HtmxTemplateHelperMixin, View):
    """Serve the folder/file rename modal with the selected item."""

    def get(self, request, bucket_name, object_type, object_path):
        object_name = object_path.rstrip('/').split('/')[-1]
        html = render_to_string(
            'dashboard/partials/rename_object_modal.html',
            {
                'modal_open': True,
                'form_action': reverse('storage:rename_object_htmx', args=[bucket_name, object_type, object_path]),
                'current_name': object_name,
                'new_name': object_name,
                'object_type': object_type,
                'object_path': object_path,
                'bucket_name': bucket_name,
                'error': None,
                'oob': False,
                'csrf_token': get_token(request),
            },
            request=request,
        )
        return HttpResponse(html)


@method_decorator(archivist_required, name='dispatch')
class RenameBucketHTMXView(HtmxTemplateHelperMixin, View):
    """Handle HTMX bucket rename requests."""

    def post(self, request, bucket_name):
        try:
            new_name = (request.POST.get('newName') or request.POST.get('prompt') or '').strip()
            if not new_name and request.body:
                try:
                    raw_body = request.body.decode(request.encoding or 'utf-8')
                    if request.content_type == 'application/json':
                        payload = json.loads(raw_body)
                        new_name = (payload.get('newName') or payload.get('prompt') or '').strip()
                    elif request.content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
                        form_data = QueryDict(raw_body)
                        new_name = (form_data.get('newName') or form_data.get('prompt') or '').strip()
                        if not new_name and raw_body.startswith('{'):
                            try:
                                parsed = json.loads(raw_body)
                            except ValueError:
                                try:
                                    parsed = ast.literal_eval(raw_body)
                                except (ValueError, SyntaxError):
                                    parsed = {}
                            new_name = (parsed.get('newName') or parsed.get('prompt') or '').strip()
                except (ValueError, TypeError):
                    new_name = ''

            if not new_name:
                error_html = render_to_string(
                    'dashboard/partials/rename_bucket_modal.html',
                    {
                        'modal_open': True,
                        'form_action': reverse('storage:rename_bucket_htmx', args=[bucket_name]),
                        'current_name': bucket_name,
                        'new_name': '',
                        'error': 'Bucket name is required',
                        'oob': False,
                        'csrf_token': get_token(request),
                    },
                    request=request,
                )
                return HttpResponse(error_html, status=400)

            bucket_service = BucketService(skip_bucket_check=True)
            result = bucket_service.rename_bucket(bucket_name, new_name)

            if not result.get('success'):
                error_html = render_to_string(
                    'dashboard/partials/rename_bucket_modal.html',
                    {
                        'modal_open': True,
                        'form_action': reverse('storage:rename_bucket_htmx', args=[bucket_name]),
                        'current_name': bucket_name,
                        'new_name': new_name,
                        'error': result.get('error', 'Rename failed'),
                        'oob': False,
                        'csrf_token': get_token(request),
                    },
                    request=request,
                )
                return HttpResponse(error_html, status=400)

            content_html = self.render_bucket_content_template(request, new_name)

            response_html = self.build_bucket_tabs_oob_response(
                main_html=content_html,
                request=request,
                active_bucket=new_name,
                success_message=None
            )

            modal_html = render_to_string(
                'dashboard/partials/rename_bucket_modal.html',
                {
                    'modal_open': False,
                    'form_action': reverse('storage:rename_bucket_htmx', args=[new_name]),
                    'current_name': new_name,
                    'new_name': '',
                    'error': None,
                    'oob': True,
                    'csrf_token': get_token(request),
                },
                request=request,
            )

            return HttpResponse(response_html + modal_html)

        except Exception as e:
            logger.exception(f"Error renaming bucket {bucket_name}: {str(e)}")
            return HttpResponse(f"Error renaming bucket: {str(e)}", status=500)
