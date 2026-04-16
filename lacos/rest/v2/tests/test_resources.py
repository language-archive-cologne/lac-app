import pytest
from unittest.mock import patch
from django.contrib.auth.models import Group

from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME
from lacos.users.models import CollectionManagerAssignment


def _assign_collection_manager(user, collection) -> None:
    group = Group.objects.get_or_create(name=COLLECTION_MANAGER_GROUP_NAME)[0]
    user.groups.add(group)
    CollectionManagerAssignment.objects.create(user=user, collection=collection)


@pytest.mark.django_db
class TestResourceDetail:
    def test_resource_metadata_by_uuid(self, api_client, media_resource, bundle_with_metadata, store_acl):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        response = api_client.get(f"/api/v2/resources/{media_resource.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "recording.wav"
        assert data["mime_type"] == "audio/x-wav"
        assert "content_url" in data

    def test_resource_by_file_pid(self, api_client, media_resource, bundle_with_metadata, store_acl):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        response = api_client.get(
            f"/api/v2/resources/{media_resource.file_pid}/"
        )
        assert response.status_code == 200

    def test_resource_not_found(self, api_client):
        response = api_client.get("/api/v2/resources/nonexistent/")
        assert response.status_code == 404

    def test_restricted_resource_metadata_is_public(self, api_client, media_resource):
        response = api_client.get(f"/api/v2/resources/{media_resource.id}/")
        assert response.status_code == 200

    def test_orphan_resource_metadata_not_found(self, api_client, orphan_media_resource_with_s3):
        response = api_client.get(f"/api/v2/resources/{orphan_media_resource_with_s3.id}/")
        assert response.status_code == 404

    def test_restricted_resource_metadata_allows_assigned_collection_manager(
        self,
        api_client,
        media_resource,
        bundle_with_metadata,
        store_acl,
        user,
    ):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )
        collection = bundle_with_metadata.structural_info.first().is_member_of_collection
        _assign_collection_manager(user, collection)

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/resources/{media_resource.id}/")

        assert response.status_code == 200


@pytest.mark.django_db
class TestResourceContent:
    @patch("lacos.rest.v2.views.resources.PresignedUrlCacheService")
    def test_public_resource_redirects(
        self, mock_cache_cls, api_client, media_resource_with_s3, bundle_with_metadata, store_acl
    ):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        mock_cache_cls.return_value.get_download_url.return_value = {
            "url": "https://s3.example.com/presigned-url",
            "filename": "recording.wav",
            "expires_in": 86400,
            "curl_command": "curl ...",
        }
        response = api_client.get(
            f"/api/v2/resources/{media_resource_with_s3.id}/content/"
        )
        assert response.status_code == 302

    def test_resource_without_auth_denied(self, api_client, media_resource):
        response = api_client.get(
            f"/api/v2/resources/{media_resource.id}/content/"
        )
        assert response.status_code == 401

    def test_restricted_resource_content_requires_access(self, api_client, media_resource, bundle_with_metadata, store_acl):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )

        response = api_client.get(
            f"/api/v2/resources/{media_resource.id}/content/"
        )

        assert response.status_code == 401

    @patch("lacos.rest.v2.views.resources.PresignedUrlCacheService")
    def test_restricted_resource_content_allows_assigned_collection_manager(
        self,
        mock_cache_cls,
        api_client,
        media_resource_with_s3,
        bundle_with_metadata,
        store_acl,
        user,
    ):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )
        collection = bundle_with_metadata.structural_info.first().is_member_of_collection
        _assign_collection_manager(user, collection)
        mock_cache_cls.return_value.get_download_url.return_value = {
            "url": "https://s3.example.com/presigned-url",
            "filename": "recording.wav",
            "expires_in": 86400,
            "curl_command": "curl ...",
        }

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/resources/{media_resource_with_s3.id}/content/")

        assert response.status_code == 302

    def test_orphan_resource_content_not_found(self, api_client, orphan_media_resource_with_s3):
        response = api_client.get(
            f"/api/v2/resources/{orphan_media_resource_with_s3.id}/content/"
        )
        assert response.status_code == 404
