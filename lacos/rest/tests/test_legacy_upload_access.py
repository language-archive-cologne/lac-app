import pytest
from django.contrib.auth.models import Group

from lacos.blam.models.collection.collection_repository import Collection
from lacos.rest.legacy_upload_access import build_legacy_upload_denied_response
from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME
from lacos.users.models import CollectionManagerAssignment


@pytest.mark.django_db
def test_build_legacy_upload_denied_response_rejects_anonymous():
    class AnonymousUser:
        is_authenticated = False

    response = build_legacy_upload_denied_response(
        AnonymousUser(),
        path_hint="restricted-collection/uploads",
    )

    assert response is not None
    assert response.status_code == 401


@pytest.mark.django_db
def test_build_legacy_upload_denied_response_rejects_unassigned_user(user):
    Collection.objects.create(identifier="restricted-collection")

    response = build_legacy_upload_denied_response(
        user,
        path_hint="restricted-collection/uploads",
    )

    assert response is not None
    assert response.status_code == 403


@pytest.mark.django_db
def test_build_legacy_upload_denied_response_allows_collection_manager(user):
    collection = Collection.objects.create(identifier="managed-collection")
    group, _ = Group.objects.get_or_create(name=COLLECTION_MANAGER_GROUP_NAME)
    user.groups.add(group)
    CollectionManagerAssignment.objects.create(user=user, collection=collection)

    response = build_legacy_upload_denied_response(
        user,
        path_hint="managed-collection/uploads",
    )

    assert response is None
