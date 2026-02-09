import pytest

from lacos.storage.constants import WAC_AGENT, WAC_AUTHENTICATED_AGENT
from lacos.storage.utils.acl_display import format_agent_uri_for_display


# =============================================================================
# Happy path: all documented URI prefix stripping cases
# =============================================================================


@pytest.mark.parametrize(
    "uri,expected",
    [
        # Special agent classes
        (WAC_AGENT, "Everyone"),
        (WAC_AUTHENTICATED_AGENT, "Authenticated"),
        # urn:lacos:eppn: -> strip prefix
        ("urn:lacos:eppn:alice@uni.org", "alice@uni.org"),
        ("urn:lacos:eppn:bob@example.com", "bob@example.com"),
        # urn:lacos:user: -> show as "user:x"
        ("urn:lacos:user:bob", "user:bob"),
        ("urn:lacos:user:admin", "user:admin"),
        # urn:lacos:group: -> keep "group:" prefix
        ("urn:lacos:group:researchers", "group:researchers"),
        ("urn:lacos:group:editors", "group:editors"),
        # urn:lacos:agent: -> show as "agent:x"
        ("urn:lacos:agent:something", "agent:something"),
        ("urn:lacos:agent:crawler-bot", "agent:crawler-bot"),
        # mailto: -> keep as-is
        ("mailto:user@example.org", "mailto:user@example.org"),
        # https: -> keep as-is
        ("https://example.org/user", "https://example.org/user"),
        # http: -> keep as-is
        ("http://example.org/user", "http://example.org/user"),
    ],
)
def test_happy_path(uri, expected):
    assert format_agent_uri_for_display(uri) == expected


# =============================================================================
# Edge cases
# =============================================================================


class TestEdgeCases:
    """Edge cases: empty, None, whitespace, and unknown URIs."""

    def test_none_returns_empty(self):
        assert format_agent_uri_for_display(None) == ""

    def test_empty_string_returns_empty(self):
        assert format_agent_uri_for_display("") == ""

    def test_whitespace_only_returns_empty(self):
        assert format_agent_uri_for_display("   ") == ""
        assert format_agent_uri_for_display("\t\n") == ""

    def test_unknown_uri_returned_as_is(self):
        assert format_agent_uri_for_display("ftp://files.example.org") == "ftp://files.example.org"

    def test_plain_string_returned_as_is(self):
        assert format_agent_uri_for_display("someuser") == "someuser"

    def test_email_like_string_returned_as_is(self):
        """A bare email (no urn:lacos:eppn: prefix) is returned unchanged."""
        assert format_agent_uri_for_display("user@example.org") == "user@example.org"


# =============================================================================
# Boundary: urn:lacos: URIs with unknown sub-prefixes
# =============================================================================


class TestUnknownUrnLacosSubprefixes:
    """URIs starting with urn:lacos: but not matching a known sub-prefix."""

    def test_custom_subprefix_returned_as_is(self):
        assert format_agent_uri_for_display("urn:lacos:custom:foo") == "urn:lacos:custom:foo"

    def test_org_subprefix_returned_as_is(self):
        assert format_agent_uri_for_display("urn:lacos:org:myorg") == "urn:lacos:org:myorg"

    def test_bare_urn_lacos_returned_as_is(self):
        """Just 'urn:lacos:' with nothing after it."""
        assert format_agent_uri_for_display("urn:lacos:") == "urn:lacos:"


# =============================================================================
# Constants consistency
# =============================================================================


class TestConstantsUsed:
    """Verify the function works with the actual constant values."""

    def test_wac_agent_constant_value(self):
        assert WAC_AGENT == "foaf:Agent"
        assert format_agent_uri_for_display("foaf:Agent") == "Everyone"

    def test_wac_authenticated_agent_constant_value(self):
        assert WAC_AUTHENTICATED_AGENT == "acl:AuthenticatedAgent"
        assert format_agent_uri_for_display("acl:AuthenticatedAgent") == "Authenticated"
