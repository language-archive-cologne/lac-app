import pytest
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
class TestAuthValidate:
    def test_validate_with_valid_token(self, api_client, user):
        token = str(AccessToken.for_user(user))
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api_client.post("/api/v2/auth/validate/")
        assert response.status_code == 200
        assert response.json()["username"] == user.username

    def test_validate_with_invalid_token(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer invalidtoken")
        response = api_client.post("/api/v2/auth/validate/")
        assert response.status_code == 401

    def test_validate_without_token(self, api_client):
        response = api_client.post("/api/v2/auth/validate/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestSessionToken:
    def test_session_token_with_logged_in_user(self, api_client, user):
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/v2/auth/session-token/")
        assert response.status_code == 200
        data = response.json()
        assert "access" in data
        assert "refresh" in data

    def test_session_token_without_session(self, api_client):
        response = api_client.post("/api/v2/auth/session-token/")
        assert response.status_code in (401, 403)
