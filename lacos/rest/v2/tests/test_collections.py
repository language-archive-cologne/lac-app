import pytest


@pytest.mark.django_db
class TestCollectionList:
    def test_list_returns_200(self, api_client):
        response = api_client.get("/api/v2/collections/")
        assert response.status_code == 200

    def test_list_contains_jsonld_context(self, api_client, collection_with_metadata):
        response = api_client.get("/api/v2/collections/")
        assert "@context" in response.json()

    def test_list_returns_collections(self, api_client, collection_with_metadata):
        data = api_client.get("/api/v2/collections/").json()
        assert data["count"] >= 1
        assert len(data["results"]) >= 1

    def test_content_type_is_jsonld(self, api_client):
        response = api_client.get("/api/v2/collections/")
        assert "application/ld+json" in response["Content-Type"]


@pytest.mark.django_db
class TestCollectionDetail:
    def test_detail_by_uuid(self, api_client, collection_with_metadata):
        response = api_client.get(
            f"/api/v2/collections/{collection_with_metadata.id}/"
        )
        assert response.status_code == 200

    def test_detail_by_handle(self, api_client, collection_with_metadata):
        response = api_client.get(
            f"/api/v2/collections/{collection_with_metadata.identifier}/"
        )
        assert response.status_code == 200

    def test_detail_contains_blam_jsonld(self, api_client, collection_with_metadata):
        data = api_client.get(
            f"/api/v2/collections/{collection_with_metadata.id}/"
        ).json()
        assert data["@type"] == "BLAMCollectionRepository"
        assert "@context" in data

    def test_detail_not_found(self, api_client):
        response = api_client.get("/api/v2/collections/nonexistent/")
        assert response.status_code == 404
