import pytest


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


@pytest.mark.django_db
class TestBundleDetail:
    def test_detail_by_uuid(self, api_client, bundle_with_metadata):
        response = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/")
        assert response.status_code == 200

    def test_detail_contains_blam_jsonld(self, api_client, bundle_with_metadata):
        data = api_client.get(f"/api/v2/bundles/{bundle_with_metadata.id}/").json()
        assert data["@type"] == "BLAMBundleRepository"

    def test_detail_not_found(self, api_client):
        response = api_client.get("/api/v2/bundles/nonexistent/")
        assert response.status_code == 404
