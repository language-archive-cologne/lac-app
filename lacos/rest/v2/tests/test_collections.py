import pytest

from lacos.storage.constants import WAC_AUTHENTICATED_AGENT

@pytest.mark.django_db
class TestCollectionList:
    def test_list_returns_200(self, api_client):
        response = api_client.get("/api/v2/collections/")
        assert response.status_code == 200

    def test_list_contains_jsonld_context(self, api_client, collection_with_metadata):
        response = api_client.get("/api/v2/collections/")
        assert "@context" in response.json()

    def test_list_returns_collections(self, api_client, collection_with_metadata, store_acl):
        store_acl(collection_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        data = api_client.get("/api/v2/collections/").json()
        assert data["count"] >= 1
        assert len(data["results"]) >= 1

    def test_content_type_is_jsonld(self, api_client):
        response = api_client.get("/api/v2/collections/")
        assert "application/ld+json" in response["Content-Type"]

    def test_invalid_limit_returns_400(self, api_client):
        response = api_client.get("/api/v2/collections/?limit=abc")
        assert response.status_code == 400

    def test_negative_offset_returns_400(self, api_client):
        response = api_client.get("/api/v2/collections/?offset=-1")
        assert response.status_code == 400

    def test_invalid_ordering_returns_400(self, api_client):
        response = api_client.get("/api/v2/collections/?ordering=does_not_exist")
        assert response.status_code == 400

    def test_list_excludes_restricted_collections_for_anonymous(
        self,
        api_client,
        collection_with_metadata,
        store_acl,
    ):
        public_collection = collection_with_metadata
        restricted_collection = type(collection_with_metadata).objects.create(
            identifier="hdl:11341/0000-0000-0000-PRIVATE-COL"
        )
        store_acl(public_collection, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        store_acl(
            restricted_collection,
            [{"agentClass": "foaf:Person", "agent": "urn:test:allowed", "mode": ["acl:Read"]}],
        )

        data = api_client.get("/api/v2/collections/").json()
        result_ids = {item["uuid"] for item in data["results"]}

        assert str(public_collection.id) in result_ids
        assert str(restricted_collection.id) not in result_ids

    def test_list_allows_authenticated_agent_collections(
        self,
        api_client,
        collection_with_metadata,
        store_acl,
        user,
    ):
        store_acl(collection_with_metadata, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])

        api_client.force_authenticate(user=user)
        data = api_client.get("/api/v2/collections/").json()
        result_ids = {item["uuid"] for item in data["results"]}

        assert str(collection_with_metadata.id) in result_ids


@pytest.mark.django_db
class TestCollectionDetail:
    def test_detail_by_uuid(self, api_client, collection_with_metadata, store_acl):
        store_acl(collection_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        response = api_client.get(
            f"/api/v2/collections/{collection_with_metadata.id}/"
        )
        assert response.status_code == 200

    def test_detail_by_handle(self, api_client, collection_with_metadata, store_acl):
        store_acl(collection_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        response = api_client.get(
            f"/api/v2/collections/{collection_with_metadata.identifier}/"
        )
        assert response.status_code == 200

    def test_detail_contains_blam_jsonld(self, api_client, collection_with_metadata, store_acl):
        store_acl(collection_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        data = api_client.get(
            f"/api/v2/collections/{collection_with_metadata.id}/"
        ).json()
        assert data["@type"] == "BLAMCollectionRepository"
        assert "@context" in data

    def test_detail_not_found(self, api_client):
        response = api_client.get("/api/v2/collections/nonexistent/")
        assert response.status_code == 404

    def test_detail_requires_acl_access(self, api_client, collection_with_metadata, store_acl):
        store_acl(
            collection_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:allowed", "mode": ["acl:Read"]}],
        )

        response = api_client.get(f"/api/v2/collections/{collection_with_metadata.id}/")
        assert response.status_code == 401

    def test_detail_allows_authenticated_agent(self, api_client, collection_with_metadata, store_acl, user):
        store_acl(collection_with_metadata, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/collections/{collection_with_metadata.id}/")
        assert response.status_code == 200
