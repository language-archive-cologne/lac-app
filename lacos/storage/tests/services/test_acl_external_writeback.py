"""
End-to-end and edge-case tests for the external WAC-aligned acl.json write-back.

Covers the full dashboard flow (edit modal -> DB -> explicit save -> S3),
the bundle save path, mixed/group/unicode/legacy data, native-user agents,
and cache freshness after write-back.
"""

import json

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import ACL_LEVEL_ACADEMIC, ACL_LEVEL_PUBLIC, ACL_LEVEL_RESTRICTED
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.permissions import ARCHIVIST_GROUP_NAME

from .test_constants import TEST_BUCKET_NAME


def _make_archivist(django_user_model, username="archivist"):
    user = django_user_model.objects.create_user(username, f"{username}@example.com", "pass")
    group, _ = Group.objects.get_or_create(name=ARCHIVIST_GROUP_NAME)
    user.groups.add(group)
    return user


def _create_collection(identifier="col-ext", key_prefix="collections/col-ext"):
    collection = Collection.objects.create(identifier=identifier)
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = key_prefix
    collection.save()
    return collection


def _create_bundle(collection, identifier="bundle-ext", key_prefix="collections/col-ext/bundle-ext"):
    bundle = Bundle.objects.create(identifier=identifier)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    bundle.import_bucket = TEST_BUCKET_NAME
    bundle.import_object_key = key_prefix
    bundle.save()
    return bundle


def _create_permissions(obj, permissions_data, model):
    ct = ContentType.objects.get_for_model(model)
    return ACLPermissions.objects.create(
        content_type=ct,
        object_id=str(obj.pk),
        permissions_data=permissions_data,
    )


def _read_acl(mock_s3, key):
    return mock_s3.get_object(Bucket=TEST_BUCKET_NAME, Key=key)["Body"].read().decode("utf-8")


# =============================================================================
# Service-level write-back edge cases
# =============================================================================


@pytest.mark.django_db
def test_save_bundle_writes_external_eppn_agents(mock_s3, acl_sync_service):
    """The bundle save path serializes externally just like collections."""
    collection = _create_collection()
    bundle = _create_bundle(collection)
    _create_permissions(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": ["acl:Read"]}],
        Bundle,
    )

    result = acl_sync_service.save_bundle(bundle)

    assert result.success is True
    raw = _read_acl(mock_s3, result.key)
    assert json.loads(raw) == [{"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]}]
    assert "urn:lacos:" not in raw
    assert "foaf:Person" not in raw


@pytest.mark.django_db
def test_save_mixed_rules_with_group_passthrough(mock_s3, acl_sync_service):
    """Public + EPPN + group rules: only the EPPN rule changes shape externally."""
    collection = _create_collection()
    _create_permissions(
        collection,
        [
            {"agentClass": "foaf:Agent", "mode": ["acl:Read"]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": ["acl:Read"]},
            {"agentClass": "foaf:Group", "agent": "urn:lacos:group:curators", "mode": ["acl:Read"]},
        ],
        Collection,
    )

    result = acl_sync_service.save_collection(collection)

    assert result.success is True
    assert json.loads(_read_acl(mock_s3, result.key)) == [
        {"agentClass": "foaf:Agent", "mode": ["acl:Read"]},
        {"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]},
        {"agentClass": "foaf:Group", "agent": "urn:lacos:group:curators", "mode": ["acl:Read"]},
    ]


@pytest.mark.django_db
def test_save_native_user_agent_passes_through(mock_s3, acl_sync_service):
    """urn:lacos:user:* (native Django users, no EPPN) has no agreed external
    form yet and must pass through unchanged so the round trip stays lossless;
    only the foaf:Person annotation is dropped."""
    collection = _create_collection()
    _create_permissions(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:lacos:user:localadmin", "mode": ["acl:Read"]}],
        Collection,
    )

    result = acl_sync_service.save_collection(collection)

    assert result.success is True
    raw = _read_acl(mock_s3, result.key)
    assert json.loads(raw) == [{"agent": "urn:lacos:user:localadmin", "mode": ["acl:Read"]}]
    assert "foaf:Person" not in raw


@pytest.mark.django_db
def test_save_legacy_bare_eppn_in_db_written_bare(mock_s3, acl_sync_service):
    """Unnormalized legacy DB data (bare EPPN + foaf:Person) still serializes cleanly."""
    collection = _create_collection()
    _create_permissions(
        collection,
        [{"agentClass": "foaf:Person", "agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]}],
        Collection,
    )

    result = acl_sync_service.save_collection(collection)

    assert result.success is True
    raw = _read_acl(mock_s3, result.key)
    assert json.loads(raw) == [{"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]}]
    assert "foaf:Person" not in raw


@pytest.mark.django_db
def test_save_preserves_additional_modes(mock_s3, acl_sync_service):
    collection = _create_collection()
    _create_permissions(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": ["acl:Read", "acl:Write"]}],
        Collection,
    )

    result = acl_sync_service.save_collection(collection)

    assert json.loads(_read_acl(mock_s3, result.key)) == [
        {"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read", "acl:Write"]}
    ]


@pytest.mark.django_db
def test_save_unicode_eppn_roundtrip(mock_s3, acl_sync_service):
    """NFC unicode EPPNs survive the S3 write/read cycle byte-exactly."""
    internal = [
        {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:müller@uni-köln.de", "mode": ["acl:Read"]}
    ]
    collection = _create_collection()
    ct = ContentType.objects.get_for_model(Collection)
    _create_permissions(collection, internal, Collection)

    save_result = acl_sync_service.save_collection(collection)
    assert json.loads(_read_acl(mock_s3, save_result.key)) == [
        {"agent": "müller@uni-köln.de", "mode": ["acl:Read"]}
    ]

    load_result = acl_sync_service.load_collection(collection, force_refresh=True)
    assert load_result.success is True
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))
    assert record.permissions_data == internal


@pytest.mark.django_db
def test_cached_load_is_fresh_after_save(mock_s3, acl_sync_service):
    """Write-back invalidates the ACL cache, so a normal cached load sees the new data."""
    collection = _create_collection()
    ct = ContentType.objects.get_for_model(Collection)

    # Prime the cache with the old public ACL
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="collections/col-ext/extensions/0013-acl/acl.json",
        Body=json.dumps([{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}]),
    )
    assert acl_sync_service.load_collection(collection).success is True

    # Change to restricted in DB and write back
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))
    internal = [
        {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": ["acl:Read"]}
    ]
    record.permissions_data = internal
    record.save(update_fields=["permissions_data"])
    assert acl_sync_service.save_collection(collection).success is True

    # A cached (non-forced) load must reflect the new external file
    assert acl_sync_service.load_collection(collection).success is True
    record.refresh_from_db()
    assert record.permissions_data == internal


# =============================================================================
# End-to-end dashboard flows: edit modal -> DB -> explicit save -> S3
# =============================================================================


@pytest.mark.django_db
def test_dashboard_edit_restricted_then_save_writes_external_acl(
    mock_s3, acl_sync_service, client, django_user_model
):
    """The real user flow: restrict to EPPNs in the edit modal, then save to S3."""
    client.force_login(_make_archivist(django_user_model))
    collection = _create_collection()

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": ACL_LEVEL_RESTRICTED,
            "extra_user_agents": "fmondac1@uni-koeln.de, adebbel1@uni-koeln.de",
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )
    assert response.status_code == 302

    # DB keeps the internal representation
    ct = ContentType.objects.get_for_model(Collection)
    record = ACLPermissions.objects.get(content_type=ct, object_id=str(collection.pk))
    assert record.permissions_data == [
        {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:adebbel1@uni-koeln.de", "mode": ["acl:Read"]},
        {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": ["acl:Read"]},
    ]

    response = client.post(reverse("storage:acl_save_single", args=["collection", str(collection.pk)]))
    assert response.status_code == 302

    raw = _read_acl(mock_s3, "collections/col-ext/extensions/0013-acl/acl.json")
    assert json.loads(raw) == [
        {"agent": "adebbel1@uni-koeln.de", "mode": ["acl:Read"]},
        {"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]},
    ]
    assert "urn:lacos:" not in raw
    assert "foaf:Person" not in raw


@pytest.mark.django_db
def test_dashboard_edit_with_selected_shibboleth_user_then_save(
    mock_s3, acl_sync_service, client, django_user_model
):
    """Selecting a Shibboleth user in the modal ends up as their bare EPPN in S3."""
    client.force_login(_make_archivist(django_user_model))
    shibboleth_user = django_user_model.objects.create_user(
        "fmondac1@uni-koeln.de",
        "fmondac1@uni-koeln.de",
        "pass",
        saml_persistent_id="persistent-id-123",
    )

    collection = _create_collection()

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": ACL_LEVEL_RESTRICTED,
            "user_ids": [str(shibboleth_user.pk)],
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )
    assert response.status_code == 302

    shibboleth_user.refresh_from_db()
    assert shibboleth_user.acl_agent_uri == "urn:lacos:eppn:fmondac1@uni-koeln.de"

    response = client.post(reverse("storage:acl_save_single", args=["collection", str(collection.pk)]))
    assert response.status_code == 302

    raw = _read_acl(mock_s3, "collections/col-ext/extensions/0013-acl/acl.json")
    assert json.loads(raw) == [{"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]}]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "access_level,expected_rules",
    [
        (ACL_LEVEL_PUBLIC, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}]),
        (ACL_LEVEL_ACADEMIC, [{"agentClass": "acl:AuthenticatedAgent", "mode": ["acl:Read"]}]),
    ],
)
def test_dashboard_edit_class_levels_then_save(
    mock_s3, acl_sync_service, client, django_user_model, access_level, expected_rules
):
    """Public/authenticated set via the modal are written to S3 unchanged."""
    client.force_login(_make_archivist(django_user_model))
    collection = _create_collection()

    response = client.post(
        reverse("storage:acl_update_permission"),
        data={
            "object_type": "collection",
            "object_id": str(collection.pk),
            "access_level": access_level,
            "next": reverse("storage:acl_admin_dashboard"),
        },
    )
    assert response.status_code == 302

    response = client.post(reverse("storage:acl_save_single", args=["collection", str(collection.pk)]))
    assert response.status_code == 302

    raw = _read_acl(mock_s3, "collections/col-ext/extensions/0013-acl/acl.json")
    assert json.loads(raw) == expected_rules


@pytest.mark.django_db
def test_dashboard_save_all_writes_external_shape_for_all_objects(
    mock_s3, acl_sync_service, client, django_user_model
):
    """acl_save_all serializes every collection and bundle externally."""
    client.force_login(_make_archivist(django_user_model))
    collection = _create_collection()
    bundle = _create_bundle(collection)
    _create_permissions(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": ["acl:Read"]}],
        Collection,
    )
    _create_permissions(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:adebbel1@uni-koeln.de", "mode": ["acl:Read"]}],
        Bundle,
    )

    response = client.post(reverse("storage:acl_save_all"), data={"scope": "all"})
    assert response.status_code == 302

    collection_raw = _read_acl(mock_s3, "collections/col-ext/extensions/0013-acl/acl.json")
    bundle_raw = _read_acl(mock_s3, "collections/col-ext/bundle-ext/extensions/0013-acl/acl.json")
    assert json.loads(collection_raw) == [{"agent": "fmondac1@uni-koeln.de", "mode": ["acl:Read"]}]
    assert json.loads(bundle_raw) == [{"agent": "adebbel1@uni-koeln.de", "mode": ["acl:Read"]}]
    for raw in (collection_raw, bundle_raw):
        assert "urn:lacos:" not in raw
        assert "foaf:Person" not in raw
