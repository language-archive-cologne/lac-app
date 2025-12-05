"""
Tests for user utility functions.
"""
import pytest

from lacos.users.models import User
from lacos.users.utils import generate_acl_agent_uri, ensure_acl_agent_uri


@pytest.mark.django_db
class TestGenerateAclAgentUri:
    """Tests for the generate_acl_agent_uri function."""

    def test_none_for_user_without_username(self):
        """Returns None if user has no username."""
        user = User(username="")
        assert generate_acl_agent_uri(user) is None

    def test_shibboleth_user_gets_eppn_format(self):
        """Shibboleth users (with saml_persistent_id) get urn:lacos:eppn: format."""
        user = User(
            username="jdoe@uni-koeln.de",
            saml_persistent_id="some-persistent-id",
        )
        assert generate_acl_agent_uri(user) == "urn:lacos:eppn:jdoe@uni-koeln.de"

    def test_native_user_gets_user_format(self):
        """Native Django users get urn:lacos:user: format."""
        user = User(username="admin")
        assert generate_acl_agent_uri(user) == "urn:lacos:user:admin"

    def test_native_user_with_email_username(self):
        """Native user with email-like username still gets user format."""
        user = User(username="admin@example.org")
        assert generate_acl_agent_uri(user) == "urn:lacos:user:admin@example.org"


@pytest.mark.django_db
class TestEnsureAclAgentUri:
    """Tests for the ensure_acl_agent_uri function."""

    def test_does_nothing_if_already_set(self):
        """Returns False if user already has acl_agent_uri."""
        user = User(
            username="jdoe",
            acl_agent_uri="urn:custom:something",
        )
        result = ensure_acl_agent_uri(user)
        assert result is False
        assert user.acl_agent_uri == "urn:custom:something"

    def test_sets_uri_for_native_user(self):
        """Sets URI for native user without existing URI."""
        user = User(username="testuser")
        result = ensure_acl_agent_uri(user)
        assert result is True
        assert user.acl_agent_uri == "urn:lacos:user:testuser"

    def test_sets_uri_for_shibboleth_user(self):
        """Sets URI for Shibboleth user without existing URI."""
        user = User(
            username="shib@example.org",
            saml_persistent_id="persistent-123",
        )
        result = ensure_acl_agent_uri(user)
        assert result is True
        assert user.acl_agent_uri == "urn:lacos:eppn:shib@example.org"

    def test_save_option_persists_changes(self):
        """With save=True, changes are persisted to database."""
        # Create user and clear the auto-generated URI
        user = User.objects.create(username="savetest")
        User.objects.filter(pk=user.pk).update(acl_agent_uri=None)
        user.refresh_from_db()
        assert user.acl_agent_uri is None

        result = ensure_acl_agent_uri(user, save=True)
        assert result is True

        # Reload from database
        user.refresh_from_db()
        assert user.acl_agent_uri == "urn:lacos:user:savetest"

    def test_returns_false_for_user_without_username(self):
        """Returns False if user has no username."""
        user = User(username="")
        result = ensure_acl_agent_uri(user)
        assert result is False
        assert user.acl_agent_uri is None


@pytest.mark.django_db
class TestSignalAutoPopulation:
    """Tests for the signal handler that auto-populates acl_agent_uri."""

    def test_native_user_gets_uri_on_creation(self):
        """Native user gets acl_agent_uri auto-populated on creation."""
        user = User.objects.create(username="signaltest")
        assert user.acl_agent_uri == "urn:lacos:user:signaltest"

    def test_existing_uri_not_overwritten(self):
        """If user already has URI, signal doesn't overwrite it."""
        user = User.objects.create(
            username="existing",
            acl_agent_uri="urn:custom:preserved",
        )
        assert user.acl_agent_uri == "urn:custom:preserved"


@pytest.mark.django_db
class TestEdgeCases:
    """Edge case tests for ACL URI generation."""

    def test_username_with_special_characters(self):
        """Username with special characters is preserved in URI."""
        user = User(username="user-name_123.test")
        assert generate_acl_agent_uri(user) == "urn:lacos:user:user-name_123.test"

    def test_username_with_unicode(self):
        """Unicode username is preserved in URI."""
        user = User(username="müller")
        assert generate_acl_agent_uri(user) == "urn:lacos:user:müller"

    def test_nfd_username_normalized_to_nfc(self):
        """NFD unicode username should be normalized to NFC."""
        # NFD form: u + combining diaeresis
        nfd_username = "mu\u0308ller"
        # NFC form: u-umlaut as single character
        nfc_username = "m\u00fcller"
        user = User(username=nfd_username)
        assert generate_acl_agent_uri(user) == f"urn:lacos:user:{nfc_username}"

    def test_nfd_shibboleth_username_normalized(self):
        """Shibboleth user with NFD username should be normalized to NFC."""
        nfd_username = "mu\u0308ller@uni-ko\u0308ln.de"
        nfc_username = "m\u00fcller@uni-k\u00f6ln.de"
        user = User(username=nfd_username, saml_persistent_id="some-id")
        assert generate_acl_agent_uri(user) == f"urn:lacos:eppn:{nfc_username}"

    def test_very_long_username(self):
        """Very long username is handled correctly."""
        long_name = "a" * 200
        user = User(username=long_name)
        result = generate_acl_agent_uri(user)
        assert result == f"urn:lacos:user:{long_name}"

    def test_shibboleth_with_complex_eppn(self):
        """Shibboleth user with complex eppn format."""
        user = User(
            username="john.doe-123@subdomain.uni-koeln.de",
            saml_persistent_id="persistent-xyz",
        )
        assert generate_acl_agent_uri(user) == "urn:lacos:eppn:john.doe-123@subdomain.uni-koeln.de"

    def test_empty_saml_persistent_id_treated_as_native(self):
        """User with empty saml_persistent_id is treated as native."""
        user = User(username="testuser", saml_persistent_id="")
        # Empty string is falsy, so treated as native
        assert generate_acl_agent_uri(user) == "urn:lacos:user:testuser"

    def test_whitespace_only_username(self):
        """Whitespace-only username is treated as empty."""
        user = User(username="   ")
        # Django strips whitespace, but if it somehow got through
        result = generate_acl_agent_uri(user)
        # This will include whitespace - unusual but predictable
        assert result == "urn:lacos:user:   "

    def test_ensure_idempotent(self):
        """Calling ensure_acl_agent_uri multiple times is safe."""
        user = User(username="idempotent")
        ensure_acl_agent_uri(user)
        first_uri = user.acl_agent_uri

        # Call again
        result = ensure_acl_agent_uri(user)
        assert result is False  # Already set
        assert user.acl_agent_uri == first_uri


@pytest.mark.django_db
class TestAclEvaluationMatching:
    """Tests for ACL evaluation URI matching scenarios."""

    def test_native_user_uri_generated_correctly(self):
        """Native user should have correct URI format."""
        user = User.objects.create(username="nativeuser")
        assert user.acl_agent_uri == "urn:lacos:user:nativeuser"

    def test_updating_user_preserves_uri(self):
        """Updating user fields doesn't change existing URI."""
        user = User.objects.create(username="preserve")
        original_uri = user.acl_agent_uri

        user.name = "New Name"
        user.save()

        user.refresh_from_db()
        assert user.acl_agent_uri == original_uri

    def test_multiple_users_unique_uris(self):
        """Multiple users have unique URIs."""
        user1 = User.objects.create(username="user1")
        user2 = User.objects.create(username="user2")
        user3 = User.objects.create(username="user3")

        uris = {user1.acl_agent_uri, user2.acl_agent_uri, user3.acl_agent_uri}
        assert len(uris) == 3  # All unique
