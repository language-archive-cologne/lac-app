from django.urls import resolve
from django.urls import reverse


def test_token_obtain():
    assert reverse("api:v2:token-obtain") == "/api/v2/auth/token/"
    assert resolve("/api/v2/auth/token/").view_name == "api:v2:token-obtain"


def test_session_token():
    assert reverse("api:v2:session-token") == "/api/v2/auth/session-token/"
    assert resolve("/api/v2/auth/session-token/").view_name == "api:v2:session-token"


def test_revoke_token():
    assert reverse("api:v2:token-revoke") == "/api/v2/auth/token/revoke/"
    assert resolve("/api/v2/auth/token/revoke/").view_name == "api:v2:token-revoke"


def test_validate_token():
    assert reverse("api:v2:auth-validate") == "/api/v2/auth/validate/"
    assert resolve("/api/v2/auth/validate/").view_name == "api:v2:auth-validate"
