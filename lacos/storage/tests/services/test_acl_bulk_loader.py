from unittest.mock import MagicMock

import pytest
from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import ACL_LEVEL_PUBLIC
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.acl_bulk_loader import load_collection_bundle_acls
from lacos.storage.services.acl_service import ACLResult


def _link_bundle(collection: Collection, identifier: str) -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _successful_result(bundle: Bundle) -> ACLResult:
    return ACLResult(
        obj=bundle,
        bucket="mock-bucket",
        key=f"{bundle.identifier}/acl.json",
        success=True,
    )


@pytest.mark.django_db
def test_load_collection_bundle_acls_loads_only_missing_bundles():
    collection = Collection.objects.create(identifier="col-alpha")
    missing_one = _link_bundle(collection, "bundle-a")
    missing_two = _link_bundle(collection, "bundle-b")
    ready_bundle = _link_bundle(collection, "bundle-c")

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(ready_bundle.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    acl_service = MagicMock()
    acl_service.load_bundle.side_effect = lambda bundle, force_refresh=True: _successful_result(bundle)

    summary = load_collection_bundle_acls(
        collection,
        "missing",
        acl_service=acl_service,
    )

    assert summary["mode"] == "missing"
    assert summary["total"] == 2
    assert summary["loaded"] == 2
    assert summary["errors"] == 0
    assert summary["failed_bundles"] == []
    assert [call.args[0].identifier for call in acl_service.load_bundle.call_args_list] == [
        missing_one.identifier,
        missing_two.identifier,
    ]


@pytest.mark.django_db
def test_load_collection_bundle_acls_reloads_all_bundles():
    collection = Collection.objects.create(identifier="col-beta")
    first_bundle = _link_bundle(collection, "bundle-a")
    second_bundle = _link_bundle(collection, "bundle-b")
    third_bundle = _link_bundle(collection, "bundle-c")

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(first_bundle.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    acl_service = MagicMock()
    acl_service.load_bundle.side_effect = lambda bundle, force_refresh=True: _successful_result(bundle)

    summary = load_collection_bundle_acls(
        collection,
        "all",
        acl_service=acl_service,
    )

    assert summary["mode"] == "all"
    assert summary["total"] == 3
    assert summary["loaded"] == 3
    assert summary["errors"] == 0
    assert [call.args[0].identifier for call in acl_service.load_bundle.call_args_list] == [
        first_bundle.identifier,
        second_bundle.identifier,
        third_bundle.identifier,
    ]


@pytest.mark.django_db
def test_load_collection_bundle_acls_returns_empty_summary_for_collection_without_bundles():
    collection = Collection.objects.create(identifier="col-empty")
    acl_service = MagicMock()

    summary = load_collection_bundle_acls(
        collection,
        "missing",
        acl_service=acl_service,
    )

    assert summary["total"] == 0
    assert summary["loaded"] == 0
    assert summary["errors"] == 0
    assert summary["failed_bundles"] == []
    acl_service.load_bundle.assert_not_called()


@pytest.mark.django_db
def test_load_collection_bundle_acls_returns_empty_summary_when_all_bundles_already_have_acl():
    collection = Collection.objects.create(identifier="col-ready")
    ready_one = _link_bundle(collection, "bundle-a")
    ready_two = _link_bundle(collection, "bundle-b")

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(ready_one.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )
    ACLPermissions.objects.create(
        content_type=bundle_ct,
        object_id=str(ready_two.pk),
        access_level=ACL_LEVEL_PUBLIC,
    )

    acl_service = MagicMock()

    summary = load_collection_bundle_acls(
        collection,
        "missing",
        acl_service=acl_service,
    )

    assert summary["total"] == 0
    assert summary["loaded"] == 0
    assert summary["errors"] == 0
    assert summary["failed_bundles"] == []
    acl_service.load_bundle.assert_not_called()


@pytest.mark.django_db
def test_load_collection_bundle_acls_continues_after_bundle_error():
    collection = Collection.objects.create(identifier="col-errors")
    broken_bundle = _link_bundle(collection, "bundle-a")
    okay_bundle = _link_bundle(collection, "bundle-b")

    acl_service = MagicMock()

    def _load_bundle(bundle, force_refresh=True):
        if bundle.pk == broken_bundle.pk:
            raise RuntimeError("S3 unavailable")
        return _successful_result(bundle)

    acl_service.load_bundle.side_effect = _load_bundle

    summary = load_collection_bundle_acls(
        collection,
        "all",
        acl_service=acl_service,
    )

    assert summary["total"] == 2
    assert summary["loaded"] == 1
    assert summary["errors"] == 1
    assert summary["failed_bundles"] == [broken_bundle.identifier]
    assert [call.args[0].identifier for call in acl_service.load_bundle.call_args_list] == [
        broken_bundle.identifier,
        okay_bundle.identifier,
    ]
