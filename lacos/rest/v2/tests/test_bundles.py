import pytest
from django.contrib.auth.models import Group

from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME
from lacos.storage.constants import WAC_AUTHENTICATED_AGENT
from lacos.storage.services.exposure_policy_service import ExposurePolicyService
from lacos.users.models import CollectionManagerAssignment


def _assign_collection_manager(user, collection) -> None:
    group = Group.objects.get_or_create(name=COLLECTION_MANAGER_GROUP_NAME)[0]
    user.groups.add(group)
    CollectionManagerAssignment.objects.create(user=user, collection=collection)


@pytest.mark.django_db
class TestBundleList:
    def test_list_returns_200(self, api_client):
        response = api_client.get("/api/v2/bundles/")
        assert response.status_code == 200

    def test_filter_by_collection(self, api_client, bundle_with_metadata, store_acl):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        col = bundle_with_metadata.structural_info.first().is_member_of_collection
        response = api_client.get(f"/api/v2/bundles/?collection={col.id}")
        assert response.status_code == 200
        assert response.json()["count"] >= 1

    def test_invalid_limit_returns_400(self, api_client):
        response = api_client.get("/api/v2/bundles/?limit=abc")
        assert response.status_code == 400

    def test_negative_offset_returns_400(self, api_client):
        response = api_client.get("/api/v2/bundles/?offset=-1")
        assert response.status_code == 400

    def test_invalid_ordering_returns_400(self, api_client):
        response = api_client.get("/api/v2/bundles/?ordering=does_not_exist")
        assert response.status_code == 400

    def test_list_includes_restricted_bundles_for_anonymous(
        self,
        api_client,
        bundle_with_metadata,
        store_acl,
    ):
        public_bundle = bundle_with_metadata
        restricted_bundle = type(bundle_with_metadata).objects.create(
            identifier="hdl:11341/0000-0000-0000-PRIVATE-BDL"
        )
        structural_info = public_bundle.structural_info.first()
        type(structural_info).objects.create(
            bundle=restricted_bundle,
            is_member_of_collection=structural_info.is_member_of_collection,
        )

        store_acl(public_bundle, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        store_acl(
            restricted_bundle,
            [{"agentClass": "foaf:Person", "agent": "urn:test:allowed", "mode": ["acl:Read"]}],
        )

        data = api_client.get("/api/v2/bundles/").json()
        result_ids = {item["uuid"] for item in data["results"]}

        assert str(public_bundle.id) in result_ids
        assert str(restricted_bundle.id) in result_ids

    def test_list_includes_restricted_bundle_for_assigned_manager(
        self,
        api_client,
        bundle_with_metadata,
        store_acl,
        user,
    ):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:allowed", "mode": ["acl:Read"]}],
        )
        collection = bundle_with_metadata.structural_info.first().is_member_of_collection
        _assign_collection_manager(user, collection)

        api_client.force_authenticate(user=user)
        data = api_client.get("/api/v2/bundles/").json()
        result_ids = {item["uuid"] for item in data["results"]}

        assert str(bundle_with_metadata.id) in result_ids

    def test_list_obeys_exposure_policy_bundle_filter(
        self,
        api_client,
        bundle_with_metadata,
        monkeypatch,
    ):
        def _filter_bundle_queryset(self, user, queryset, *, channel):
            assert channel == "api"
            return queryset.exclude(pk=bundle_with_metadata.pk)

        monkeypatch.setattr(
            ExposurePolicyService,
            "filter_bundle_queryset",
            _filter_bundle_queryset,
        )

        data = api_client.get("/api/v2/bundles/").json()
        result_ids = {item["uuid"] for item in data["results"]}

        assert str(bundle_with_metadata.id) not in result_ids


@pytest.mark.django_db
class TestBundleDetail:
    def test_detail_by_uuid(self, api_client, bundle_with_metadata, store_acl):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")
        assert response.status_code == 200

    def test_detail_contains_blam_jsonld(self, api_client, bundle_with_metadata, store_acl):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        data = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/").json()
        assert data["@type"] == "BLAMBundleRepository"

    def test_detail_not_found(self, api_client):
        response = api_client.get("/api/v2/bundles/nonexistent/")
        assert response.status_code == 404

    def test_detail_exposes_restricted_metadata_anonymously(self, api_client, bundle_with_metadata, store_acl):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")
        assert response.status_code == 200

    def test_detail_allows_authenticated_agent(self, api_client, bundle_with_metadata, store_acl, user):
        store_acl(bundle_with_metadata, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])
        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")
        assert response.status_code == 200

    def test_detail_allows_assigned_collection_manager(self, api_client, bundle_with_metadata, store_acl, user):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:allowed", "mode": ["acl:Read"]}],
        )
        collection = bundle_with_metadata.structural_info.first().is_member_of_collection
        _assign_collection_manager(user, collection)

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")

        assert response.status_code == 200
