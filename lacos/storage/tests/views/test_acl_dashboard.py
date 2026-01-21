import pytest

from urllib.parse import parse_qs, urlparse

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.contrib.auth.models import Group

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import (
    ACL_LEVEL_PUBLIC,
    ACL_LEVEL_RESTRICTED,
)
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
    assert "Collections" in html


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
