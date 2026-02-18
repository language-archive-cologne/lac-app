import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import ACL_LEVEL_ACADEMIC, ACL_LEVEL_PUBLIC, ACL_LEVEL_RESTRICTED
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_bundle_for_collection(collection: Collection, identifier: str) -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


@pytest.mark.django_db
def test_collection_detail_shows_bundle_access_summary_by_main_levels(client):
    collection = Collection.objects.create(identifier="hdl:11341/test-summary-1")
    bundle_public = _create_bundle_for_collection(collection, "bundle-public")
    bundle_academic = _create_bundle_for_collection(collection, "bundle-academic")
    bundle_restricted = _create_bundle_for_collection(collection, "bundle-restricted")

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

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))
    assert response.status_code == 200

    summary = response.context["bundle_access_summary"]
    assert summary == {"public": 1, "academic": 1, "restricted": 1, "total": 3}

    page = response.content.decode("utf-8")
    assert "Public 1" in page
    assert "Academic 1" in page
    assert "Restricted 1" in page
    assert "Missing" not in page


@pytest.mark.django_db
def test_collection_detail_uses_collection_acl_as_fallback_for_bundle_summary(client):
    collection = Collection.objects.create(identifier="hdl:11341/test-summary-2")
    bundle_without_acl = _create_bundle_for_collection(collection, "bundle-fallback")
    bundle_public = _create_bundle_for_collection(collection, "bundle-public-explicit")
    assert bundle_without_acl.pk != bundle_public.pk

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    collection_ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=collection_ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_ACADEMIC,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(bundle_public.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))
    assert response.status_code == 200

    summary = response.context["bundle_access_summary"]
    assert summary == {"public": 1, "academic": 1, "restricted": 0, "total": 2}
