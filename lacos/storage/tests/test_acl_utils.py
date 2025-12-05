import pytest

from lacos.storage.constants import (
    ACL_LEVEL_EMBARGO,
    ACL_LEVEL_PRIVATE,
    ACL_LEVEL_PROTECTED,
    ACL_LEVEL_PUBLIC,
    WAC_AGENT,
    WAC_AUTHENTICATED_AGENT,
    WAC_READ,
)
from lacos.storage.utils.acl import (
    determine_access_level,
    extract_read_agents,
    normalize_agent_uri,
    normalize_permissions_data,
)


@pytest.mark.parametrize(
    "entries,expected",
    [
        ([], ACL_LEVEL_EMBARGO),
        (None, ACL_LEVEL_EMBARGO),
        ([{"mode": [WAC_READ], "agent": "user@example.org"}], ACL_LEVEL_PRIVATE),
        ([{"mode": [WAC_READ], "agentClass": WAC_AUTHENTICATED_AGENT}], ACL_LEVEL_PROTECTED),
        ([{"mode": [WAC_READ], "agentClass": WAC_AGENT}], ACL_LEVEL_PUBLIC),
        (
            [
                {"mode": [WAC_READ], "agent": "user1"},
                {"mode": [WAC_READ], "agentClass": WAC_AUTHENTICATED_AGENT},
            ],
            ACL_LEVEL_PROTECTED,
        ),
    ],
)
def test_determine_access_level(entries, expected):
    assert determine_access_level(entries) == expected


def test_extract_read_agents_deduplicates_and_orders():
    entries = [
        {"mode": [WAC_READ], "agent": "user1"},
        {"mode": [WAC_READ], "agentClass": WAC_AUTHENTICATED_AGENT},
        {"mode": [WAC_READ], "agent": "user1"},
        {"mode": [WAC_READ], "agentClass": WAC_AGENT},
    ]

    agents = extract_read_agents(entries)
    assert agents == ["user1", WAC_AUTHENTICATED_AGENT, WAC_AGENT]


# =============================================================================
# Tests for normalize_agent_uri
# =============================================================================


class TestNormalizeAgentUri:
    """Tests for the normalize_agent_uri function."""

    def test_none_returns_none(self):
        assert normalize_agent_uri(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_agent_uri("") is None
        assert normalize_agent_uri("   ") is None

    def test_eppn_format_gets_lacos_prefix(self):
        """URIs with @ but no prefix should get urn:lacos:eppn: prefix."""
        assert normalize_agent_uri("user@uni-koeln.de") == "urn:lacos:eppn:user@uni-koeln.de"
        assert normalize_agent_uri("jdoe@example.org") == "urn:lacos:eppn:jdoe@example.org"

    def test_eppn_with_whitespace_is_trimmed(self):
        assert normalize_agent_uri("  user@uni-koeln.de  ") == "urn:lacos:eppn:user@uni-koeln.de"

    def test_plain_string_gets_agent_prefix(self):
        """Plain strings without @ get urn:lacos:agent: prefix."""
        assert normalize_agent_uri("someuser") == "urn:lacos:agent:someuser"
        assert normalize_agent_uri("admin") == "urn:lacos:agent:admin"

    def test_urn_lacos_preserved(self):
        """URIs already with urn:lacos: prefix are preserved."""
        assert normalize_agent_uri("urn:lacos:eppn:user@example.org") == "urn:lacos:eppn:user@example.org"
        assert normalize_agent_uri("urn:lacos:user:admin") == "urn:lacos:user:admin"
        assert normalize_agent_uri("urn:lacos:agent:foo") == "urn:lacos:agent:foo"

    def test_mailto_preserved(self):
        """mailto: URIs are preserved as-is."""
        assert normalize_agent_uri("mailto:user@example.org") == "mailto:user@example.org"

    def test_https_preserved(self):
        """https: URIs are preserved as-is."""
        assert normalize_agent_uri("https://example.org/users/123") == "https://example.org/users/123"

    def test_http_preserved(self):
        """http: URIs are preserved as-is."""
        assert normalize_agent_uri("http://example.org/agent/foo") == "http://example.org/agent/foo"

    def test_other_urn_preserved(self):
        """Other urn: schemes are preserved as-is."""
        assert normalize_agent_uri("urn:oid:1.2.3.4") == "urn:oid:1.2.3.4"
        assert normalize_agent_uri("urn:uuid:123-456") == "urn:uuid:123-456"

    # Edge cases

    def test_multiple_at_symbols(self):
        """URI with multiple @ symbols still gets eppn prefix."""
        # This is unusual but should still be treated as eppn-like
        assert normalize_agent_uri("user@dept@uni-koeln.de") == "urn:lacos:eppn:user@dept@uni-koeln.de"

    def test_unicode_in_uri(self):
        """Unicode characters in URI are preserved."""
        assert normalize_agent_uri("müller@uni-köln.de") == "urn:lacos:eppn:müller@uni-köln.de"
        assert normalize_agent_uri("用户") == "urn:lacos:agent:用户"

    def test_special_characters_in_plain_string(self):
        """Special characters in plain strings are preserved."""
        assert normalize_agent_uri("user-name_123") == "urn:lacos:agent:user-name_123"
        assert normalize_agent_uri("user.name") == "urn:lacos:agent:user.name"

    def test_uri_with_port(self):
        """https URI with port is preserved."""
        assert normalize_agent_uri("https://example.org:8080/user/123") == "https://example.org:8080/user/123"

    def test_uri_with_query_string(self):
        """https URI with query string is preserved."""
        assert normalize_agent_uri("https://example.org/user?id=123") == "https://example.org/user?id=123"

    def test_uri_with_fragment(self):
        """https URI with fragment is preserved."""
        assert normalize_agent_uri("https://example.org/user#section") == "https://example.org/user#section"

    def test_case_sensitivity_of_prefix(self):
        """Prefix matching should be case-sensitive."""
        # Uppercase prefixes should NOT be recognized and should get normalized
        assert normalize_agent_uri("URN:LACOS:user:test") == "urn:lacos:agent:URN:LACOS:user:test"
        assert normalize_agent_uri("MAILTO:user@example.org") == "urn:lacos:eppn:MAILTO:user@example.org"

    def test_only_at_symbol(self):
        """Just @ symbol gets eppn prefix."""
        assert normalize_agent_uri("@") == "urn:lacos:eppn:@"

    def test_at_at_start_or_end(self):
        """@ at unusual positions."""
        assert normalize_agent_uri("@domain.org") == "urn:lacos:eppn:@domain.org"
        assert normalize_agent_uri("user@") == "urn:lacos:eppn:user@"

    def test_very_long_uri(self):
        """Very long URIs are handled correctly."""
        long_user = "a" * 500 + "@example.org"
        result = normalize_agent_uri(long_user)
        assert result == f"urn:lacos:eppn:{long_user}"
        assert len(result) > 500

    def test_newlines_and_tabs_stripped(self):
        """Newlines and tabs in whitespace are stripped."""
        assert normalize_agent_uri("\n\tuser@example.org\n\t") == "urn:lacos:eppn:user@example.org"

    def test_internal_whitespace_preserved(self):
        """Internal whitespace (if any) is preserved after strip."""
        # Unusual but possible
        assert normalize_agent_uri("user name@example.org") == "urn:lacos:eppn:user name@example.org"


# =============================================================================
# Tests for normalize_permissions_data
# =============================================================================


class TestNormalizePermissionsData:
    """Tests for the normalize_permissions_data function."""

    def test_none_returns_none(self):
        assert normalize_permissions_data(None) is None

    def test_empty_list_returns_empty_list(self):
        assert normalize_permissions_data([]) == []

    def test_public_acl_unchanged(self):
        """Public ACL (foaf:Agent) has no agent URI to normalize."""
        entries = [{"agentClass": WAC_AGENT, "mode": [WAC_READ]}]
        result = normalize_permissions_data(entries)
        assert result == [{"agentClass": WAC_AGENT, "mode": [WAC_READ]}]

    def test_authenticated_acl_unchanged(self):
        """Authenticated ACL has no agent URI to normalize."""
        entries = [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": [WAC_READ]}]
        result = normalize_permissions_data(entries)
        assert result == [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": [WAC_READ]}]

    def test_eppn_agent_normalized(self):
        """Agent with eppn format gets normalized to urn:lacos:eppn:"""
        entries = [
            {"agentClass": "foaf:Person", "agent": "user@uni-koeln.de", "mode": [WAC_READ]}
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@uni-koeln.de", "mode": [WAC_READ]}
        ]

    def test_multiple_entries_normalized(self):
        """Multiple entries are all normalized."""
        entries = [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "user1@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "user2@example.org", "mode": [WAC_READ]},
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user1@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user2@example.org", "mode": [WAC_READ]},
        ]

    def test_already_normalized_preserved(self):
        """Already normalized URIs are preserved."""
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]}
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]}
        ]

    def test_mixed_formats_normalized(self):
        """Mixed formats: some normalized, some preserved."""
        entries = [
            {"agentClass": "foaf:Person", "agent": "external@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "mailto:special@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:internal@example.org", "mode": [WAC_READ]},
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:external@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "mailto:special@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:internal@example.org", "mode": [WAC_READ]},
        ]

    def test_original_entries_not_mutated(self):
        """Original entries should not be mutated."""
        entries = [
            {"agentClass": "foaf:Person", "agent": "user@example.org", "mode": [WAC_READ]}
        ]
        original_agent = entries[0]["agent"]
        normalize_permissions_data(entries)
        assert entries[0]["agent"] == original_agent  # Original unchanged

    # Edge cases

    def test_entry_without_agent_field(self):
        """Entries without agent field are preserved as-is."""
        entries = [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "mode": [WAC_READ]},  # No agent
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "mode": [WAC_READ]},
        ]

    def test_entry_with_none_agent(self):
        """Entry with None agent is preserved."""
        entries = [{"agentClass": "foaf:Person", "agent": None, "mode": [WAC_READ]}]
        result = normalize_permissions_data(entries)
        assert result == [{"agentClass": "foaf:Person", "agent": None, "mode": [WAC_READ]}]

    def test_entry_with_empty_agent(self):
        """Entry with empty string agent becomes None after normalization."""
        entries = [{"agentClass": "foaf:Person", "agent": "", "mode": [WAC_READ]}]
        result = normalize_permissions_data(entries)
        assert result == [{"agentClass": "foaf:Person", "agent": None, "mode": [WAC_READ]}]

    def test_entry_with_non_string_agent(self):
        """Entry with non-string agent is preserved (unusual but possible)."""
        entries = [{"agentClass": "foaf:Person", "agent": 123, "mode": [WAC_READ]}]
        result = normalize_permissions_data(entries)
        assert result == [{"agentClass": "foaf:Person", "agent": 123, "mode": [WAC_READ]}]

    def test_non_dict_entries_preserved(self):
        """Non-dict entries in the list are preserved as-is."""
        entries = [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            "not a dict",
            123,
            None,
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            "not a dict",
            123,
            None,
        ]

    def test_extra_fields_preserved(self):
        """Extra fields in entries are preserved."""
        entries = [
            {
                "agentClass": "foaf:Person",
                "agent": "user@example.org",
                "mode": [WAC_READ],
                "custom_field": "value",
                "another": 123,
            }
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {
                "agentClass": "foaf:Person",
                "agent": "urn:lacos:eppn:user@example.org",
                "mode": [WAC_READ],
                "custom_field": "value",
                "another": 123,
            }
        ]

    def test_multiple_modes(self):
        """Entries with multiple modes are handled correctly."""
        entries = [
            {"agentClass": "foaf:Person", "agent": "user@example.org", "mode": [WAC_READ, "acl:Write", "acl:Control"]}
        ]
        result = normalize_permissions_data(entries)
        assert result[0]["mode"] == [WAC_READ, "acl:Write", "acl:Control"]
        assert result[0]["agent"] == "urn:lacos:eppn:user@example.org"

    def test_group_agent_normalized(self):
        """foaf:Group agents are also normalized."""
        entries = [
            {"agentClass": "foaf:Group", "agent": "researchers@uni-koeln.de", "mode": [WAC_READ]}
        ]
        result = normalize_permissions_data(entries)
        assert result == [
            {"agentClass": "foaf:Group", "agent": "urn:lacos:eppn:researchers@uni-koeln.de", "mode": [WAC_READ]}
        ]

    def test_deeply_nested_not_affected(self):
        """Only top-level agent field is normalized, not nested ones."""
        entries = [
            {
                "agentClass": "foaf:Person",
                "agent": "user@example.org",
                "mode": [WAC_READ],
                "metadata": {"nested_agent": "other@example.org"},
            }
        ]
        result = normalize_permissions_data(entries)
        # Top-level agent normalized
        assert result[0]["agent"] == "urn:lacos:eppn:user@example.org"
        # Nested agent NOT normalized (not our concern)
        assert result[0]["metadata"]["nested_agent"] == "other@example.org"

    def test_large_list_performance(self):
        """Large lists are handled without issues."""
        entries = [
            {"agentClass": "foaf:Person", "agent": f"user{i}@example.org", "mode": [WAC_READ]}
            for i in range(1000)
        ]
        result = normalize_permissions_data(entries)
        assert len(result) == 1000
        assert result[0]["agent"] == "urn:lacos:eppn:user0@example.org"
        assert result[999]["agent"] == "urn:lacos:eppn:user999@example.org"
