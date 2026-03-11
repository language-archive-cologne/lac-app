import pytest
from unittest.mock import patch


@pytest.mark.django_db
class TestMediaByHandle:
    @patch("lacos.rest.v2.views.media.PresignedUrlCacheService")
    @patch("lacos.rest.v2.views.resources.ACLEvaluationService")
    def test_resolve_handle_to_redirect(
        self, mock_acl_cls, mock_cache_cls, api_client, media_resource_with_s3
    ):
        mock_acl_cls.return_value.can_read_bundle.return_value = True
        mock_cache_cls.return_value.get_download_url.return_value = {
            "url": "https://s3.example.com/presigned-url",
            "filename": "recording.wav",
            "expires_in": 86400,
            "curl_command": "curl ...",
        }
        handle = media_resource_with_s3.file_pid
        response = api_client.get(f"/api/v2/media/{handle}/")
        assert response.status_code == 302

    def test_unknown_handle_404(self, api_client):
        response = api_client.get("/api/v2/media/hdl:11341/nonexistent/")
        assert response.status_code == 404
