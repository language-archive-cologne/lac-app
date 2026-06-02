import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from urllib.parse import parse_qs, urlparse

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.contrib.auth.models import Group

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import (
    ACL_LEVEL_ACADEMIC,
    ACL_LEVEL_PUBLIC,
    ACL_LEVEL_RESTRICTED,
)
from lacos.storage.models import BackgroundTask
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.permissions import ARCHIVIST_GROUP_NAME


def _make_archivist(user):
    group, _ = Group.objects.get_or_create(name=ARCHIVIST_GROUP_NAME)
    user.groups.add(group)
    return user


@pytest.mark.django_db
def test_acl_update_permission_creates_record(client, django_user_model):
    user = django_user_model.objects.create_user("owner", "owner@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-1")

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": ACL_LEVEL_PUBLIC,
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )

    assert response.status_code == 302
    assert "message=" in response.url

    ct = ContentType.objects.get_for_model(Collection)
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))
    assert record.access_level == ACL_LEVEL_PUBLIC
    assert record.last_synced is not None


@pytest.mark.django_db
def test_acl_update_permission_updates_existing_record(client, django_user_model):
    user = django_user_model.objects.create_user("editor", "editor@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    bundle = Bundle.objects.create(identifier="bundle-1")
    ct = ContentType.objects.get_for_model(Bundle)
    record = ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(bundle.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "bundle",
            "object_id": str(bundle.pk),
            "permission_id": str(record.pk),
            "access_level": ACL_LEVEL_RESTRICTED,
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.access_level == ACL_LEVEL_RESTRICTED
    assert record.permissions_data == []


@pytest.mark.django_db
def test_acl_update_permission_rejects_invalid_level(client, django_user_model):
    user = django_user_model.objects.create_user("viewer", "viewer@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-2")

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": "invalid",
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(response.url).query)
    assert query["message"] == ["Invalid access level selected."]
    ct = ContentType.objects.get_for_model(Collection)
    assert not ACLPermissions.objects.filter(content_type=ct, object_id=str(collection.pk)).exists()


@pytest.mark.django_db
def test_acl_records_panel_renders(client, django_user_model):
    user = django_user_model.objects.create_user("viewer", "viewer@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    response = client.get(reverse("storage:acl_records_panel"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "id=\"acl-records-table\"" in html
    assert "id=\"acl-records-action-status\"" in html


@pytest.mark.django_db
def test_acl_records_table_uses_synced_search_and_delegated_edit_modal(
    client, django_user_model
):
    user = django_user_model.objects.create_user("acl-ui", "acl-ui@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)
    Bundle.objects.create(identifier="bundle-ui")

    response = client.get(reverse("storage:acl_records_table", args=["bundle"]))

    assert response.status_code == 200
    html = response.content.decode()
    assert 'hx-trigger="change, input changed delay:400ms from:#acl-records-search-bundle"' in html
    assert 'hx-sync="this:replace"' in html
    assert "hx-preserve" in html
    assert 'hx-target="#acl-records-action-status"' in html
    assert "data-acl-edit-open" in html
    assert "showModal()" not in html


@pytest.mark.django_db
def test_acl_edit_form_uses_modal_controller_hooks(client, django_user_model):
    user = django_user_model.objects.create_user("acl-form", "acl-form@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)
    bundle = Bundle.objects.create(identifier="bundle-form")

    response = client.get(
        reverse("storage:acl_edit_permission_form", args=["bundle", str(bundle.pk)])
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "data-acl-edit-form" in html
    assert "data-acl-edit-close" in html
    assert "data-acl-access-level" in html
    assert "data-acl-agent-fields" in html
    assert "onclick=" not in html
    assert "onchange=" not in html
    assert "<script>" not in html


@pytest.mark.django_db
def test_acl_admin_dashboard_includes_acl_edit_modal_controller(
    client, django_user_model
):
    user = django_user_model.objects.create_user("acl-controller", "acl-controller@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    response = client.get(f"{reverse('storage:acl_admin_dashboard')}?tab=records&scope=bundle")

    assert response.status_code == 200
    html = response.content.decode()
    assert "function openAclEditModal()" in html
    assert "function closeAclEditModal()" in html
    assert "function toggleAclAgentFields(" in html
    assert "htmx:afterRequest" in html
    assert "[data-acl-edit-form]" in html


@pytest.mark.django_db
def test_acl_records_table_collection_rows_render_bundle_bulk_load_actions(
    client, django_user_model
):
    user = django_user_model.objects.create_user("row-viewer", "row@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-row")
    bundle = Bundle.objects.create(identifier="bundle-row")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)

    response = client.get(reverse("storage:acl_records_table", args=["collection"]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Load missing" in html
    assert "Re-load all" in html


@pytest.mark.django_db
def test_acl_load_collection_bundles_requires_archivist(client, django_user_model):
    user = django_user_model.objects.create_user("plain", "plain@example.com", "pass")
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-secure")

    response = client.post(
        reverse("storage:acl_load_collection_bundles", args=[str(collection.pk)]),
        data={"mode": "missing"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_acl_load_collection_bundles_rejects_invalid_mode(client, django_user_model):
    user = django_user_model.objects.create_user("invalid", "invalid@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-invalid")

    response = client.post(
        reverse("storage:acl_load_collection_bundles", args=[str(collection.pk)]),
        data={"mode": "bogus"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 400
    assert "Invalid mode" in response.content.decode()


@pytest.mark.django_db
def test_acl_load_collection_bundles_returns_404_for_unknown_collection(
    client, django_user_model
):
    user = django_user_model.objects.create_user("missing", "missing@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    response = client.post(
        reverse("storage:acl_load_collection_bundles", args=[str(uuid.uuid4())]),
        data={"mode": "missing"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 404


@pytest.mark.django_db
@patch("lacos.storage.views.dashboard.acl.load_collection_bundles_task")
def test_acl_load_collection_bundles_enqueues_background_task(
    mock_task, client, django_user_model
):
    user = django_user_model.objects.create_user("queue", "queue@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-queue")
    bundle = Bundle.objects.create(identifier="bundle-queue")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    mock_task.return_value = SimpleNamespace(id="huey-123")

    response = client.post(
        reverse("storage:acl_load_collection_bundles", args=[str(collection.pk)]),
        data={"mode": "missing"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200

    task_record = BackgroundTask.objects.get(task_name="acl_load_collection_bundles")
    assert task_record.metadata["collection_id"] == str(collection.pk)
    assert task_record.metadata["collection_identifier"] == collection.identifier
    assert task_record.metadata["mode"] == "missing"
    assert task_record.huey_task_id == "huey-123"

    mock_task.assert_called_once_with(
        collection_id=str(collection.pk),
        mode="missing",
        tracking_id=str(task_record.id),
    )

    html = response.content.decode()
    assert str(task_record.id) in html
    assert "Load missing" in html


@pytest.mark.django_db
@patch("lacos.storage.views.dashboard.acl.load_collection_bundles_task")
def test_acl_load_collection_bundles_returns_no_work_message_when_nothing_is_missing(
    mock_task, client, django_user_model
):
    user = django_user_model.objects.create_user("empty", "empty@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="col-empty")
    bundle = Bundle.objects.create(identifier="bundle-ready")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    response = client.post(
        reverse("storage:acl_load_collection_bundles", args=[str(collection.pk)]),
        data={"mode": "missing"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "No bundle ACLs matched this action." in response.content.decode()
    assert BackgroundTask.objects.count() == 0
    mock_task.assert_not_called()


@pytest.mark.django_db
def test_background_task_status_triggers_acl_records_refresh_for_acl_bulk_load(
    client, django_user_model
):
    user = django_user_model.objects.create_user("status", "status@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    task_record = BackgroundTask.objects.create(
        task_name="acl_load_collection_bundles",
        status=BackgroundTask.Status.SUCCESS,
        message="Loaded 2 of 2 bundle ACLs.",
        metadata={
            "collection_identifier": "col-status",
            "mode_label": "Load missing",
            "status_template": "dashboard/partials/acl_bulk_load_status.html",
            "refresh_event": "aclRecordsRefresh",
            "refresh_payload": {"scope": "collection"},
        },
        result={
            "total": 2,
            "loaded": 2,
            "errors": 0,
            "failed_bundles": [],
        },
    )

    response = client.get(reverse("storage:background_task_status", args=[str(task_record.id)]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Loaded 2" in html

    trigger = json.loads(response["HX-Trigger"])
    assert trigger["showMessage"]["level"] == "success"
    assert trigger["aclRecordsRefresh"]["scope"] == "collection"


@pytest.mark.django_db
def test_acl_records_table_sorting(client, django_user_model):
    user = django_user_model.objects.create_user("editor", "editor@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    first = Collection.objects.create(identifier="alpha")
    second = Collection.objects.create(identifier="beta")

    ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(content_type=ct, object_id=str(first.pk), access_level=ACL_LEVEL_RESTRICTED)
    ACLPermissions.objects.create(content_type=ct, object_id=str(second.pk), access_level=ACL_LEVEL_PUBLIC)

    url = reverse("storage:acl_records_table", args=["collection"])
    response = client.get(url, {"sort": "identifier", "dir": "desc"})
    assert response.status_code == 200
    html = response.content.decode()
    assert html.index("beta") < html.index("alpha")
    assert "Page 1 of" in html


@pytest.mark.django_db
def test_acl_records_table_collection_rows_include_bundle_access_summary(
    client, django_user_model
):
    user = django_user_model.objects.create_user("summary", "summary@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    target_collection = Collection.objects.create(identifier="col-summary")
    other_collection = Collection.objects.create(identifier="col-other")

    bundle_public = Bundle.objects.create(identifier="bundle-public")
    bundle_academic = Bundle.objects.create(identifier="bundle-academic")
    bundle_restricted = Bundle.objects.create(identifier="bundle-restricted")
    bundle_missing = Bundle.objects.create(identifier="bundle-missing")
    other_bundle = Bundle.objects.create(identifier="bundle-other")

    BundleStructuralInfo.objects.create(
        bundle=bundle_public, is_member_of_collection=target_collection
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle_academic, is_member_of_collection=target_collection
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle_restricted, is_member_of_collection=target_collection
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle_missing, is_member_of_collection=target_collection
    )
    BundleStructuralInfo.objects.create(bundle=other_bundle, is_member_of_collection=other_collection)

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_public.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_academic.pk),
        access_level=ACL_LEVEL_ACADEMIC,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_restricted.pk),
        access_level=ACL_LEVEL_RESTRICTED,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(other_bundle.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    response = client.get(
        reverse("storage:acl_records_table", args=["collection"]),
        {"q": "col-summary"},
    )
    assert response.status_code == 200

    html = response.content.decode()
    assert "Bundle access" in html
    assert "Public 1" in html
    assert "Academic 1" in html
    assert "Restricted 1" in html
    assert "Missing 1" in html

    row = response.context["page_obj"].object_list[0]
    summary = row["bundle_access_summary"]
    assert summary["total_bundles"] == 4
    assert summary["public_count"] == 1
    assert summary["academic_count"] == 1
    assert summary["restricted_count"] == 1
    assert summary["missing_acl_count"] == 1


@pytest.mark.django_db
def test_acl_admin_dashboard_respects_tab_query(client, django_user_model):
    user = django_user_model.objects.create_user("owner", "owner@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    response = client.get(reverse("storage:acl_admin_dashboard"), {"tab": "records"})
    assert response.status_code == 200
    assert response.context["active_tab"] == "records"


@pytest.mark.django_db
def test_acl_admin_dashboard_requires_archivist(client, django_user_model):
    user = django_user_model.objects.create_user("nonarchivist", "nonarchivist@example.com", "pass")
    client.force_login(user)

    response = client.get(reverse("storage:acl_admin_dashboard"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_acl_dashboard_panel_groups_bundle_access_by_collection(client, django_user_model):
    user = django_user_model.objects.create_user("overview1", "overview1@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    col_a = Collection.objects.create(identifier="col-a")
    col_b = Collection.objects.create(identifier="col-b")
    Collection.objects.create(identifier="col-empty")
    bundle_a1 = Bundle.objects.create(identifier="bundle-a1")
    bundle_a2 = Bundle.objects.create(identifier="bundle-a2")
    bundle_b1 = Bundle.objects.create(identifier="bundle-b1")
    BundleStructuralInfo.objects.create(bundle=bundle_a1, is_member_of_collection=col_a)
    BundleStructuralInfo.objects.create(bundle=bundle_a2, is_member_of_collection=col_a)
    BundleStructuralInfo.objects.create(bundle=bundle_b1, is_member_of_collection=col_b)

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_a1.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_a2.pk),
        access_level=ACL_LEVEL_RESTRICTED,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_b1.pk),
        access_level=ACL_LEVEL_ACADEMIC,
    )

    response = client.get(reverse("storage:acl_dashboard_panel"))
    assert response.status_code == 200

    rows = {row["collection_identifier"]: row for row in response.context["bundle_access_overview"]}
    assert rows["col-a"]["total_bundles"] == 2
    assert rows["col-a"]["public_count"] == 1
    assert rows["col-a"]["restricted_count"] == 1
    assert rows["col-a"]["academic_count"] == 0
    assert rows["col-a"]["missing_acl_count"] == 0

    assert rows["col-b"]["total_bundles"] == 1
    assert rows["col-b"]["public_count"] == 0
    assert rows["col-b"]["restricted_count"] == 0
    assert rows["col-b"]["academic_count"] == 1
    assert rows["col-b"]["missing_acl_count"] == 0

    assert rows["col-empty"]["total_bundles"] == 0
    assert rows["col-empty"]["public_count"] == 0
    assert rows["col-empty"]["restricted_count"] == 0
    assert rows["col-empty"]["academic_count"] == 0
    assert rows["col-empty"]["missing_acl_count"] == 0

    totals = response.context["bundle_access_totals"]
    assert totals["collections"] == 3
    assert totals["bundles"] == 3
    assert totals["public"] == 1
    assert totals["academic"] == 1
    assert totals["restricted"] == 1
    assert totals["missing_acl"] == 0


@pytest.mark.django_db
def test_acl_dashboard_panel_includes_unassigned_and_missing_acl_bundles(
    client, django_user_model
):
    user = django_user_model.objects.create_user("overview2", "overview2@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    col = Collection.objects.create(identifier="col-missing")
    assigned_bundle = Bundle.objects.create(identifier="bundle-assigned")
    unassigned_bundle = Bundle.objects.create(identifier="bundle-unassigned")
    BundleStructuralInfo.objects.create(bundle=assigned_bundle, is_member_of_collection=col)

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(unassigned_bundle.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    response = client.get(reverse("storage:acl_dashboard_panel"))
    assert response.status_code == 200

    rows = {row["collection_identifier"]: row for row in response.context["bundle_access_overview"]}
    assert rows["col-missing"]["total_bundles"] == 1
    assert rows["col-missing"]["missing_acl_count"] == 1

    assert rows["Unassigned"]["total_bundles"] == 1
    assert rows["Unassigned"]["public_count"] == 1
    assert rows["Unassigned"]["missing_acl_count"] == 0

    totals = response.context["bundle_access_totals"]
    assert totals["collections"] == 1
    assert totals["bundles"] == 2
    assert totals["public"] == 1
    assert totals["academic"] == 0
    assert totals["restricted"] == 0
    assert totals["missing_acl"] == 1


@pytest.mark.django_db
def test_acl_admin_dashboard_tab_dashboard_has_bundle_access_overview(
    client, django_user_model
):
    user = django_user_model.objects.create_user("overview3", "overview3@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    col = Collection.objects.create(identifier="col-main")
    bundle = Bundle.objects.create(identifier="bundle-main")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=col)

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle.pk),
        access_level=ACL_LEVEL_RESTRICTED,
    )

    response = client.get(reverse("storage:acl_admin_dashboard"), {"tab": "dashboard"})
    assert response.status_code == 200

    rows = {row["collection_identifier"]: row for row in response.context["bundle_access_overview"]}
    assert rows["col-main"]["total_bundles"] == 1
    assert rows["col-main"]["restricted_count"] == 1
    assert response.context["bundle_access_totals"]["bundles"] == 1


@pytest.mark.django_db
@patch("lacos.storage.services.acl_service.ACLService.load_collection")
def test_acl_load_single_htmx_returns_oob_table_and_status(
    mock_load_collection, client, django_user_model
):
    from lacos.storage.services.acl_service import ACLResult

    user = django_user_model.objects.create_user("loader", "loader@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="alpha-col")
    ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_RESTRICTED,
    )
    mock_load_collection.return_value = ACLResult(
        obj=collection,
        bucket="mock-bucket",
        key="alpha/acl.json",
        success=True,
    )

    response = client.post(
        reverse("storage:acl_load_single", args=["collection", str(collection.pk)]),
        data={
            "sort": "identifier",
            "dir": "asc",
            "page": "1",
            "q": "alpha",
            "status": "has_acl",
            "access": ACL_LEVEL_RESTRICTED,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Loaded ACL for collection" in html
    assert 'id="acl-records-table"' in html
    assert 'hx-swap-oob="outerHTML"' in html
    assert 'value="alpha"' in html
    mock_load_collection.assert_called_once_with(collection, force_refresh=True)


@pytest.mark.django_db
@patch("lacos.storage.services.acl_service.ACLService.save_bundle")
def test_acl_save_single_htmx_returns_oob_table_with_multiple_rows(
    mock_save_bundle, client, django_user_model
):
    from lacos.storage.services.acl_service import ACLResult

    user = django_user_model.objects.create_user("saver", "saver@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    first = Bundle.objects.create(identifier="vera-one")
    second = Bundle.objects.create(identifier="vera-two")
    ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(first.pk),
        access_level=ACL_LEVEL_RESTRICTED,
    )
    ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(second.pk),
        access_level=ACL_LEVEL_RESTRICTED,
    )
    mock_save_bundle.return_value = ACLResult(
        obj=first,
        bucket="mock-bucket",
        key="vera/acl.json",
        success=True,
    )

    response = client.post(
        reverse("storage:acl_save_single", args=["bundle", str(first.pk)]),
        data={
            "sort": "identifier",
            "dir": "asc",
            "page": "1",
            "status": "all",
            "access": "all",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Saved ACL for bundle" in html
    assert 'id="acl-records-table"' in html
    assert 'hx-swap-oob="outerHTML"' in html
    assert "vera-one" in html
    assert "vera-two" in html


@pytest.mark.django_db
@patch("lacos.storage.services.acl_service.ACLService.load_collection")
def test_acl_load_single_htmx_failure_keeps_oob_refresh_and_escapes_error(
    mock_load_collection, client, django_user_model
):
    from lacos.storage.services.acl_service import ACLResult

    user = django_user_model.objects.create_user("loader2", "loader2@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="alpha-fail")
    mock_load_collection.return_value = ACLResult(
        obj=collection,
        bucket="mock-bucket",
        key="alpha/acl.json",
        success=False,
        error="<bad>",
    )

    response = client.post(
        reverse("storage:acl_load_single", args=["collection", str(collection.pk)]),
        data={"sort": "identifier", "dir": "asc", "page": "1"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert 'hx-swap-oob="outerHTML"' in html
    assert "text-error" in html
    assert "Failed to load: &lt;bad&gt;" in html
    assert "Failed to load: <bad>" not in html
    mock_load_collection.assert_called_once_with(collection, force_refresh=True)


# ---------------------------------------------------------------------------
# Integration tests: ACL save pipeline normalization
# ---------------------------------------------------------------------------


def _mock_save_permission(perm):
    """Return a successful ACLResult without touching S3."""
    from lacos.storage.services.acl_service import ACLResult

    return ACLResult(
        obj=perm.content_object,
        bucket="mock-bucket",
        key="mock-key",
        success=True,
    )


@pytest.mark.django_db
@patch(
    "lacos.storage.services.acl_service.ACLService.save_permission",
    side_effect=_mock_save_permission,
)
def test_acl_update_permission_normalizes_bare_email(
    _mock_save, client, django_user_model
):
    """A bare email in extra_user_agents is stored as urn:lacos:eppn:<email>."""
    user = django_user_model.objects.create_user("norm1", "norm1@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="norm-col-1")

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": ACL_LEVEL_RESTRICTED,
            "extra_user_agents": "alice@uni.org",
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )

    assert response.status_code == 302

    ct = ContentType.objects.get_for_model(Collection)
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))

    assert record.access_level == ACL_LEVEL_RESTRICTED
    assert record.permissions_data is not None

    stored_agents = [
        entry["agent"] for entry in record.permissions_data if "agent" in entry
    ]
    assert "urn:lacos:eppn:alice@uni.org" in stored_agents
    assert "alice@uni.org" not in stored_agents


@pytest.mark.django_db
@patch(
    "lacos.storage.services.acl_service.ACLService.save_permission",
    side_effect=_mock_save_permission,
)
def test_acl_update_permission_preserves_full_uri(
    _mock_save, client, django_user_model
):
    """A URI already in urn:lacos:eppn: form is preserved, not double-normalized."""
    user = django_user_model.objects.create_user("norm2", "norm2@example.com", "pass")
    _make_archivist(user)
    client.force_login(user)

    collection = Collection.objects.create(identifier="norm-col-2")

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": ACL_LEVEL_RESTRICTED,
            "extra_user_agents": "urn:lacos:eppn:bob@uni.org",
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )

    assert response.status_code == 302

    ct = ContentType.objects.get_for_model(Collection)
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))

    assert record.access_level == ACL_LEVEL_RESTRICTED
    assert record.permissions_data is not None

    stored_agents = [
        entry["agent"] for entry in record.permissions_data if "agent" in entry
    ]
    assert "urn:lacos:eppn:bob@uni.org" in stored_agents
    # Ensure no double-prefixing occurred
    assert "urn:lacos:eppn:urn:lacos:eppn:bob@uni.org" not in stored_agents


@pytest.mark.django_db
@patch(
    "lacos.storage.services.acl_service.ACLService.save_permission",
    side_effect=_mock_save_permission,
)
def test_acl_update_permission_generates_missing_selected_user_acl_uri(
    _mock_save, client, django_user_model
):
    archivist = django_user_model.objects.create_user("norm3", "norm3@example.com", "pass")
    _make_archivist(archivist)
    client.force_login(archivist)

    selected_user = django_user_model.objects.create_user(
        "fmondac1@uni-koeln.de",
        password="pass",
        saml_persistent_id="persistent-id-3",
        acl_agent_uri=None,
    )
    collection = Collection.objects.create(identifier="norm-col-3")

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": ACL_LEVEL_RESTRICTED,
            "user_ids": [str(selected_user.pk)],
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )

    assert response.status_code == 302

    selected_user.refresh_from_db()
    assert selected_user.acl_agent_uri == "urn:lacos:eppn:fmondac1@uni-koeln.de"

    ct = ContentType.objects.get_for_model(Collection)
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))
    stored_agents = [
        entry["agent"] for entry in record.permissions_data if "agent" in entry
    ]
    assert "urn:lacos:eppn:fmondac1@uni-koeln.de" in stored_agents


@pytest.mark.django_db
def test_acl_edit_form_lists_and_selects_saml_user_with_generated_acl_uri(
    client, django_user_model
):
    archivist = django_user_model.objects.create_user("norm4", "norm4@example.com", "pass")
    _make_archivist(archivist)
    client.force_login(archivist)

    selected_user = django_user_model.objects.create_user(
        "fmondac1@uni-koeln.de",
        password="pass",
        saml_persistent_id="persistent-id-4",
        acl_agent_uri=None,
    )
    collection = Collection.objects.create(identifier="norm-col-4")
    ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_RESTRICTED,
        permissions_data=[
            {
                "agentClass": "foaf:Person",
                "agent": "fmondac1@uni-koeln.de",
                "mode": ["acl:Read"],
            }
        ],
        read_agents=["urn:lacos:eppn:fmondac1@uni-koeln.de"],
    )

    response = client.get(
        reverse("storage:acl_edit_permission_form", args=["collection", str(collection.pk)])
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert 'value="%s"' % selected_user.pk in html
    assert "fmondac1@uni-koeln.de" in html
    assert "urn:lacos:eppn:fmondac1@uni-koeln.de" in html
    assert f'value="{selected_user.pk}" selected' in html


@pytest.mark.django_db
def test_acl_edit_form_maps_legacy_agent_only_entry_to_selected_user(
    client, django_user_model
):
    archivist = django_user_model.objects.create_user("norm5", "norm5@example.com", "pass")
    _make_archivist(archivist)
    client.force_login(archivist)

    selected_user = django_user_model.objects.create_user(
        "fmondac1@uni-koeln.de",
        password="pass",
        saml_persistent_id="persistent-id-5",
        acl_agent_uri=None,
    )
    collection = Collection.objects.create(identifier="norm-col-5")
    ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_RESTRICTED,
        permissions_data=[
            {
                "agent": "fmondac1@uni-koeln.de",
                "mode": ["acl:Read"],
            }
        ],
        read_agents=["urn:lacos:eppn:fmondac1@uni-koeln.de"],
    )

    response = client.get(
        reverse("storage:acl_edit_permission_form", args=["collection", str(collection.pk)])
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert f'value="{selected_user.pk}" selected' in html
