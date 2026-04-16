import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.views.metadata.bundle import BundleListView, BundleOverviewView
from lacos.users.models import CollectionManagerAssignment
from lacos.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _ensure_group(name: str) -> Group:
    return Group.objects.get_or_create(name=name)[0]


def _create_bundle_for_collection(collection: Collection, identifier: str) -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _make_collection_manager(*collections: Collection):
    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))
    for collection in collections:
        CollectionManagerAssignment.objects.create(user=user, collection=collection)
    return user


def test_bundle_overview_allows_assigned_collection_manager(rf: RequestFactory):
    collection = Collection.objects.create(identifier="assigned-collection")
    bundle = _create_bundle_for_collection(collection, "assigned-bundle")
    user = _make_collection_manager(collection)

    request = rf.get(reverse("blam:bundle_metadata_overview", args=[bundle.pk]))
    request.user = user

    response = BundleOverviewView.as_view()(request, bundle_id=bundle.pk)

    assert response.status_code == 200


def test_bundle_overview_denies_unassigned_collection_manager(rf: RequestFactory):
    assigned = Collection.objects.create(identifier="assigned-collection")
    other = Collection.objects.create(identifier="other-collection")
    bundle = _create_bundle_for_collection(other, "foreign-bundle")
    user = _make_collection_manager(assigned)

    request = rf.get(reverse("blam:bundle_metadata_overview", args=[bundle.pk]))
    request.user = user

    with pytest.raises(PermissionDenied):
        BundleOverviewView.as_view()(request, bundle_id=bundle.pk)


def test_bundle_list_filters_to_assigned_collections(client):
    assigned = Collection.objects.create(identifier="assigned-collection")
    other = Collection.objects.create(identifier="other-collection")
    assigned_bundle = _create_bundle_for_collection(assigned, "assigned-bundle")
    _create_bundle_for_collection(other, "other-bundle")
    user = _make_collection_manager(assigned)
    client.force_login(user)

    response = client.get(reverse("blam:bundle_metadata_list"))

    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert assigned_bundle.identifier in html
    assert "other-bundle" not in html
