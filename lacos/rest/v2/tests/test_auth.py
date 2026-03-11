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
