import pytest

from lacos.storage.constants import WAC_AUTHENTICATED_AGENT


@pytest.mark.django_db
class TestBundleList:
    def test_list_returns_200(self, api_client):
        response = api_client.get("/api/v2/bundles/")
        assert response.status_code == 200

    def test_filter_by_collection(self, api_client, bundle_with_metadata):
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

    def test_detail_requires_acl_access(self, api_client, bundle_with_metadata, store_acl):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")
        assert response.status_code == 401

    def test_detail_allows_authenticated_agent(self, api_client, bundle_with_metadata, store_acl, user):
        store_acl(bundle_with_metadata, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])
        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")
        assert response.status_code == 200
