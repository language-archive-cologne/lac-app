"""
ACL admin dashboard views.

Handles ACL configuration, sync operations, and permission management.
"""
import logging
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.models.acl_config import ACLConfig
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.constants import ACL_LEVEL_PUBLIC, ACL_LEVEL_PROTECTED, ACL_LEVEL_PRIVATE

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


def _render_load_summary_partial(request, summary=None, error_message=None):
    """Render load summary partial template."""
    html = render_to_string(
        "dashboard/partials/acl_load_summary.html",
        {"load_summary": summary, "error_message": error_message},
        request=request,
    )
    return HttpResponse(html)


# Backwards compatibility alias
_render_sync_summary_partial = _render_load_summary_partial


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
            return _render_load_summary_partial(request, summary=summary)
        else:
            msg = f"Loaded {total_loaded} ACLs for {scope_label}"
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={msg}")

    except Exception as e:
        logger.exception("Error in acl_load_all: %s", e)
        if request.headers.get("HX-Request"):
            return _render_load_summary_partial(request, error_message=str(e))
        else:
            return redirect(f"{reverse('storage:acl_admin_dashboard')}?message=Load failed: {e}")


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


@login_required
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
    elif access_level == ACL_LEVEL_PROTECTED:
        permissions_data = [{"agentClass": "acl:AuthenticatedAgent", "mode": ["acl:Read"]}]
        read_agents = ["acl:AuthenticatedAgent"]
    elif access_level == ACL_LEVEL_PRIVATE:
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


@login_required
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

    # Get current read agents from permissions_data
    selected_user_ids = set()
    selected_group_ids = set()
    if perm and perm.permissions_data:
        for rule in perm.permissions_data:
            agent = rule.get("agent", "")
            agent_class = rule.get("agentClass", "")
            if agent_class == "foaf:Person" and agent:
                user = User.objects.filter(acl_agent_uri=agent).first()
                if user:
                    selected_user_ids.add(user.id)
            elif agent_class == "foaf:Group" and agent:
                group_acl = GroupACL.objects.filter(acl_agent_uri=agent).first()
                if group_acl:
                    selected_group_ids.add(group_acl.id)

    context = {
        "object_type": object_type,
        "object_id": object_id,
        "permission_id": perm.pk if perm else None,
        "identifier": getattr(obj, "identifier", str(obj.pk)),
        "name": _resolve_acl_display_name(obj),
        "current_access_level": perm.access_level if perm else "embargo",
        "access_level_choices": ACLPermissions.ACCESS_LEVEL_CHOICES,
        "available_users": User.objects.exclude(acl_agent_uri__isnull=True).exclude(acl_agent_uri="").order_by("username"),
        "available_groups": GroupACL.objects.exclude(acl_agent_uri__isnull=True).exclude(acl_agent_uri="").select_related("group").order_by("group__name"),
        "selected_user_ids": selected_user_ids,
        "selected_group_ids": selected_group_ids,
        "next_url": request.GET.get("next", reverse("storage:acl_records_table", args=[object_type])),
    }

    return render(request, "dashboard/partials/acl_edit_form.html", context)
