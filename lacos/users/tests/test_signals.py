"""
Tests for user authentication and security audit signals.
"""
from unittest.mock import Mock

import pytest
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

from lacos.users.models import User
from lacos.users.tests.factories import UserFactory


def _record_for(caplog, message: str):
    return next(record for record in caplog.records if record.getMessage() == message)


@pytest.mark.django_db
class TestAuthenticationLogging:
    """Tests for authentication event logging."""

    def test_login_success_logs_event(self, caplog):
        """Test that successful login is logged with user info."""
        user = UserFactory()
        request = Mock()
        request.META = {
            "HTTP_USER_AGENT": "Mozilla/5.0 Test Browser",
            "REMOTE_ADDR": "192.168.1.100",
        }

        with caplog.at_level("INFO", logger="lacos.security"):
            user_logged_in.send(sender=User, request=request, user=user)

        assert "LOGIN_SUCCESS" in caplog.text
        record = _record_for(caplog, "LOGIN_SUCCESS")
        assert record.user == user.username
        assert record.ip == "192.168.1.100"
        assert record.method == "regular"

    def test_login_success_detects_saml(self, caplog):
        """Test that SAML login method is detected."""
        user = UserFactory()
        request = Mock()
        request.META = {
            "HTTP_USER_AGENT": "Mozilla/5.0",
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_SHIB_IDENTITY_PROVIDER": "https://idp.example.com",
        }

        with caplog.at_level("INFO", logger="lacos.security"):
            user_logged_in.send(sender=User, request=request, user=user)

        assert "LOGIN_SUCCESS" in caplog.text
        record = _record_for(caplog, "LOGIN_SUCCESS")
        assert record.method == "saml"

    def test_login_success_with_forwarded_ip(self, caplog):
        """Test that X-Forwarded-For IP is extracted correctly."""
        user = UserFactory()
        request = Mock()
        request.META = {
            "HTTP_USER_AGENT": "Mozilla/5.0",
            "HTTP_X_FORWARDED_FOR": "203.0.113.50, 70.41.3.18",
            "REMOTE_ADDR": "127.0.0.1",
        }

        with caplog.at_level("INFO", logger="lacos.security"):
            user_logged_in.send(sender=User, request=request, user=user)

        record = _record_for(caplog, "LOGIN_SUCCESS")
        assert record.ip == "203.0.113.50"

    def test_logout_logs_event(self, caplog):
        """Test that logout is logged."""
        user = UserFactory()
        request = Mock()
        request.META = {"REMOTE_ADDR": "192.168.1.100"}

        with caplog.at_level("INFO", logger="lacos.security"):
            user_logged_out.send(sender=User, request=request, user=user)

        assert "LOGOUT" in caplog.text
        record = _record_for(caplog, "LOGOUT")
        assert record.user == user.username
        assert record.ip == "192.168.1.100"

    def test_logout_handles_anonymous_user(self, caplog):
        """Test that logout handles None user gracefully."""
        request = Mock()
        request.META = {"REMOTE_ADDR": "192.168.1.100"}

        with caplog.at_level("INFO", logger="lacos.security"):
            user_logged_out.send(sender=User, request=request, user=None)

        assert "LOGOUT" in caplog.text
        record = _record_for(caplog, "LOGOUT")
        assert record.user == "anonymous"

    def test_login_failed_logs_warning(self, caplog):
        """Test that failed login attempts are logged as warnings."""
        request = Mock()
        request.META = {
            "HTTP_USER_AGENT": "Mozilla/5.0 Attacker",
            "REMOTE_ADDR": "10.20.30.40",
        }
        credentials = {"username": "hacker_attempt"}

        with caplog.at_level("WARNING", logger="lacos.security"):
            user_login_failed.send(
                sender=User, credentials=credentials, request=request
            )

        assert "LOGIN_FAILED" in caplog.text
        record = _record_for(caplog, "LOGIN_FAILED")
        assert record.attempted_user == "hacker_attempt"
        assert record.ip == "10.20.30.40"


@pytest.mark.django_db
class TestUserModelLogging:
    """Tests for user model change logging."""

    def test_user_creation_logs_event(self, caplog):
        """Test that user creation is logged."""
        with caplog.at_level("INFO", logger="lacos.security"):
            user = UserFactory(username="newuser", email="new@example.com")

        assert "USER_CREATED" in caplog.text
        record = _record_for(caplog, "USER_CREATED")
        assert record.username == "newuser"
        assert record.email == "new@example.com"

    def test_user_deletion_logs_warning(self, caplog):
        """Test that user deletion is logged as warning."""
        user = UserFactory(username="deleteme", email="delete@example.com")

        with caplog.at_level("WARNING", logger="lacos.security"):
            user.delete()

        assert "USER_DELETED" in caplog.text
        record = _record_for(caplog, "USER_DELETED")
        assert record.username == "deleteme"
        assert record.email == "delete@example.com"
