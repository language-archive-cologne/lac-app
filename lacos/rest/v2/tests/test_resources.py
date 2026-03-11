import pytest
from unittest.mock import patch


@pytest.mark.django_db
class TestResourceDetail:
    def test_resource_metadata_by_uuid(self, api_client, media_resource):
        response = api_client.get(f"/api/v2/resources/{media_resource.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "recording.wav"
        assert data["mime_type"] == "audio/x-wav"
        assert "content_url" in data

    def test_resource_by_file_pid(self, api_client, media_resource):
        response = api_client.get(
            f"/api/v2/resources/{media_resource.file_pid}/"
        )
        assert response.status_code == 200

    def test_resource_not_found(self, api_client):
        response = api_client.get("/api/v2/resources/nonexistent/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestResourceContent:
    @patch("lacos.rest.v2.views.resources.PresignedUrlCacheService")
    @patch("lacos.rest.v2.views.resources.ACLEvaluationService")
    def test_public_resource_redirects(
        self, mock_acl_cls, mock_cache_cls, api_client, media_resource_with_s3
    ):
        mock_acl_cls.return_value.can_read_bundle.return_value = True
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
