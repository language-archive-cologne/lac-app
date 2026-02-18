import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import (
    ACL_LEVEL_ACADEMIC,
    ACL_LEVEL_PUBLIC,
    ACL_LEVEL_RESTRICTED,
    WAC_AUTHENTICATED_AGENT,
)
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.users.models import GroupACL
from lacos.storage.permissions import ARCHIVIST_GROUP_NAME


def _create_collection(identifier: str = "collection-eval") -> Collection:
    return Collection.objects.create(identifier=identifier)


def _create_bundle(collection: Collection, identifier: str = "bundle-eval") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _store_acl(obj, rules):
    ct = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.create(
        content_type=ct,
        object_id=obj.pk,
        ACL_file_bucket="test-bucket",
        ACL_file_key="test/key",
        permissions_data=rules,
    )


@pytest.mark.django_db
def test_public_agent_allows_anonymous():
    collection = _create_collection()
    _store_acl(collection, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])

    service = ACLEvaluationService()
    result = service.evaluate(AnonymousUser(), collection)

    assert result.allowed is True
    assert result.matched_rule["agentClass"] == "foaf:Agent"
    assert result.access_level == ACL_LEVEL_PUBLIC


@pytest.mark.django_db
def test_authenticated_agent_requires_login():
    collection = _create_collection()
    _store_acl(collection, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])

    service = ACLEvaluationService()

    anonymous_result = service.evaluate(AnonymousUser(), collection)
    assert anonymous_result.allowed is False
    assert anonymous_result.access_level == ACL_LEVEL_ACADEMIC

    user = get_user_model().objects.create_user(username="auth-user", password="test123")
    result = service.evaluate(user, collection)
    assert result.allowed is True
    assert result.access_level == ACL_LEVEL_ACADEMIC


@pytest.mark.django_db
def test_person_rule_matches_acl_agent_uri():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    person_uri = "http://example.org/users/alice"
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": person_uri, "mode": ["acl:Read"]}])

    service = ACLEvaluationService()

    user = get_user_model().objects.create_user(username="alice", password="pass", acl_agent_uri=person_uri)
    result = service.evaluate(user, bundle)
    assert result.allowed is True
    assert result.access_level == ACL_LEVEL_RESTRICTED

    other_user = get_user_model().objects.create_user(username="bob", password="pass")
    denied = service.evaluate(other_user, bundle)
    assert denied.allowed is False
    assert denied.access_level == ACL_LEVEL_RESTRICTED


@pytest.mark.django_db
def test_group_rule_matches_group_profile():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    group_uri = "http://example.org/groups/researchers"
    _store_acl(bundle, [{"agentClass": "foaf:Group", "agent": group_uri, "mode": ["acl:Read"]}])

    service = ACLEvaluationService()

    group = Group.objects.create(name="Researchers")
    GroupACL.objects.create(group=group, acl_agent_uri=group_uri)

    user = get_user_model().objects.create_user(username="groupie", password="pass")
    user.groups.add(group)

    allowed = service.evaluate(user, bundle)
    assert allowed.allowed is True
    assert allowed.access_level == ACL_LEVEL_RESTRICTED

    other_user = get_user_model().objects.create_user(username="outsider", password="pass")
    denied = service.evaluate(other_user, bundle)
    assert denied.allowed is False
    assert denied.access_level == ACL_LEVEL_RESTRICTED


@pytest.mark.django_db
def test_bundle_inherits_collection_acl():
    collection = _create_collection()
    bundle = _create_bundle(collection)

    _store_acl(collection, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/inherited", "mode": ["acl:Read"]}])

    user = get_user_model().objects.create_user(
        username="inherited",
        password="pass",
        acl_agent_uri="http://example.org/users/inherited",
    )

    service = ACLEvaluationService()
    result = service.evaluate(user, bundle)
    assert result.allowed is True
    assert result.source == collection
    assert result.access_level == ACL_LEVEL_RESTRICTED


@pytest.mark.django_db
def test_bundle_acl_takes_precedence_over_collection_acl():
    collection = _create_collection()
    bundle = _create_bundle(collection)

    _store_acl(collection, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/bundle-only", "mode": ["acl:Read"]}])

    allowed_user = get_user_model().objects.create_user(
        username="bundle-only",
        password="pass",
        acl_agent_uri="http://example.org/users/bundle-only",
    )
    other_user = get_user_model().objects.create_user(username="outsider2", password="pass")

    service = ACLEvaluationService()

    allowed = service.evaluate(allowed_user, bundle)
    assert allowed.allowed is True
    assert allowed.source == bundle
    assert allowed.access_level == ACL_LEVEL_RESTRICTED

    denied = service.evaluate(other_user, bundle)
    assert denied.allowed is False
    assert denied.source == bundle
    assert denied.default_applied is True
    assert denied.access_level == ACL_LEVEL_RESTRICTED


@pytest.mark.django_db
def test_default_deny_when_no_rules_match():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    _store_acl(bundle, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])

    service = ACLEvaluationService()
    anonymous_result = service.evaluate(AnonymousUser(), bundle)
    assert anonymous_result.allowed is False
    assert anonymous_result.default_applied is True
    assert anonymous_result.access_level == ACL_LEVEL_ACADEMIC


@pytest.mark.django_db
def test_archivist_override_allows_access():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/other", "mode": ["acl:Read"]}])

    group = Group.objects.create(name=ARCHIVIST_GROUP_NAME)
    user = get_user_model().objects.create_user(username="archivist", password="pass")
    user.groups.add(group)

    service = ACLEvaluationService()
    result = service.evaluate(user, bundle)
    assert result.allowed is True
    assert result.access_level == ACL_LEVEL_RESTRICTED


@pytest.mark.django_db
def test_missing_acl_denies_even_if_default_deny_flag_is_false():
    collection = _create_collection(identifier="collection-no-acl")
    service = ACLEvaluationService()
    service.default_deny = False

    result = service.evaluate(AnonymousUser(), collection)
    assert result.allowed is False
    assert result.default_applied is True
    assert result.reason == "No ACL data found; default deny"
