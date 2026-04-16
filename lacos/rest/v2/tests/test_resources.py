import pytest
from unittest.mock import ANY, patch
from django.contrib.auth.models import Group
from lacos.blam.models.bundle.bundle_structural_info import BundleResources, WrittenResource

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
        assert data["download_url"] == data["content_url"]
        assert data["stream_url"] == f"/api/v2/resources/{media_resource.id}/stream/"

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

    def test_non_streamable_resource_omits_stream_url(
        self,
        api_client,
        bundle_with_metadata,
        store_acl,
    ):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        resource = WrittenResource.objects.create(
            file_name="transcript.xml",
            file_pid="hdl:11341/0000-0000-0000-WR1",
            mime_type="application/xml",
        )
        BundleResources.objects.create(bundle=bundle_with_metadata).bundle_written_resources.add(resource)

        response = api_client.get(f"/api/v2/resources/{resource.id}/")

        assert response.status_code == 200
        assert "stream_url" not in response.json()

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

    def test_bundle_acl_overrides_public_collection_for_binary_access(
        self,
        api_client,
        media_resource,
        bundle_with_metadata,
        store_acl,
    ):
        collection = bundle_with_metadata.structural_info.first().is_member_of_collection
        store_acl(collection, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )

        response = api_client.get(f"/api/v2/resources/{media_resource.id}/content/")

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

    def test_restricted_resource_content_denies_manager_assigned_to_other_collection(
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
        other_collection = type(
            bundle_with_metadata.structural_info.first().is_member_of_collection
        ).objects.create(identifier="hdl:11341/0000-0000-0000-OTHER-COL")
        _assign_collection_manager(user, other_collection)

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/resources/{media_resource.id}/content/")

        assert response.status_code == 403

    def test_orphan_resource_content_not_found(self, api_client, orphan_media_resource_with_s3):
        response = api_client.get(
            f"/api/v2/resources/{orphan_media_resource_with_s3.id}/content/"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestResourceStream:
    @patch("lacos.rest.v2.views.resources.PresignedUrlCacheService")
    def test_public_resource_stream_redirects(
        self, mock_cache_cls, api_client, media_resource_with_s3, bundle_with_metadata, store_acl
    ):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        mock_cache_cls.return_value.get_presigned_url.return_value = "https://s3.example.com/presigned-stream"

        response = api_client.get(
            f"/api/v2/resources/{media_resource_with_s3.id}/stream/"
        )

        assert response.status_code == 302
        mock_cache_cls.return_value.get_presigned_url.assert_called_once_with(
            bucket="lacos-production",
            key="test-collection/test-bundle/recording.wav",
            response_headers={"ResponseContentType": "audio/x-wav"},
            auth_context=ANY,
        )

    def test_resource_stream_without_auth_denied(self, api_client, media_resource):
        response = api_client.get(
            f"/api/v2/resources/{media_resource.id}/stream/"
        )
        assert response.status_code == 401

    def test_restricted_resource_stream_requires_access(self, api_client, media_resource, bundle_with_metadata, store_acl):
        store_acl(
            bundle_with_metadata,
            [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
        )

        response = api_client.get(
            f"/api/v2/resources/{media_resource.id}/stream/"
        )

        assert response.status_code == 401

    @patch("lacos.rest.v2.views.resources.PresignedUrlCacheService")
    def test_restricted_resource_stream_allows_assigned_collection_manager(
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
        mock_cache_cls.return_value.get_presigned_url.return_value = "https://s3.example.com/presigned-stream"

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/resources/{media_resource_with_s3.id}/stream/")

        assert response.status_code == 302

    def test_restricted_resource_stream_denies_manager_assigned_to_other_collection(
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
        other_collection = type(
            bundle_with_metadata.structural_info.first().is_member_of_collection
        ).objects.create(identifier="hdl:11341/0000-0000-0000-OTHER-COL-STREAM")
        _assign_collection_manager(user, other_collection)

        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/v2/resources/{media_resource.id}/stream/")

        assert response.status_code == 403

    def test_orphan_resource_stream_not_found(self, api_client, orphan_media_resource_with_s3):
        response = api_client.get(
            f"/api/v2/resources/{orphan_media_resource_with_s3.id}/stream/"
        )
        assert response.status_code == 404

    def test_non_streamable_resource_stream_not_found(
        self,
        api_client,
        bundle_with_metadata,
        store_acl,
    ):
        store_acl(bundle_with_metadata, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
        resource = WrittenResource.objects.create(
            file_name="transcript.xml",
            file_pid="hdl:11341/0000-0000-0000-WR2",
            mime_type="application/xml",
        )
        BundleResources.objects.create(bundle=bundle_with_metadata).bundle_written_resources.add(resource)

        response = api_client.get(f"/api/v2/resources/{resource.id}/stream/")

        assert response.status_code == 404
