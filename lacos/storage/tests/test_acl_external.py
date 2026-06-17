"""
Tests for the external acl.json serializer (WAC-aligned JSON contract).

External acl.json must contain bare EPPN agents and class-based rules only:
no urn:lacos:eppn:* identifiers and no foaf:Person agentClass annotations.
"""

import json

from lacos.storage.constants import WAC_AGENT, WAC_AUTHENTICATED_AGENT, WAC_READ
from lacos.storage.utils.acl_external import (
    serialize_agent_for_acl_json,
    serialize_permissions_data_for_acl_json,
)


# =============================================================================
# Tests for serialize_agent_for_acl_json
# =============================================================================


class TestSerializeAgentForAclJson:
    def test_eppn_prefix_stripped(self):
        assert serialize_agent_for_acl_json("urn:lacos:eppn:fmondac1@uni-koeln.de") == "fmondac1@uni-koeln.de"

    def test_agent_prefix_stripped(self):
        assert serialize_agent_for_acl_json("urn:lacos:agent:someuser") == "someuser"

    def test_bare_eppn_unchanged(self):
        assert serialize_agent_for_acl_json("fmondac1@uni-koeln.de") == "fmondac1@uni-koeln.de"

    def test_mailto_unchanged(self):
        assert serialize_agent_for_acl_json("mailto:user@example.org") == "mailto:user@example.org"

    def test_https_unchanged(self):
        assert serialize_agent_for_acl_json("https://example.org/users/123") == "https://example.org/users/123"

    def test_roundtrip_with_normalize(self):
        """Serializing and re-normalizing restores the internal identifier."""
        from lacos.storage.utils.acl import normalize_agent_uri

        internal = "urn:lacos:eppn:fmondac1@uni-koeln.de"
        assert normalize_agent_uri(serialize_agent_for_acl_json(internal)) == internal

        internal = "urn:lacos:agent:someuser"
        assert normalize_agent_uri(serialize_agent_for_acl_json(internal)) == internal


# =============================================================================
# Tests for serialize_permissions_data_for_acl_json
# =============================================================================


class TestSerializePermissionsDataForAclJson:
    def test_none_returns_empty_list(self):
        assert serialize_permissions_data_for_acl_json(None) == []

    def test_empty_list_returns_empty_list(self):
        assert serialize_permissions_data_for_acl_json([]) == []

    def test_public_rule_unchanged(self):
        entries = [{"agentClass": WAC_AGENT, "mode": [WAC_READ]}]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]}
        ]

    def test_authenticated_rule_unchanged(self):
        entries = [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": [WAC_READ]}]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agentClass": WAC_AUTHENTICATED_AGENT, "mode": [WAC_READ]}
        ]

    def test_internal_eppn_rule_converted_to_bare_agent(self):
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": [WAC_READ]}
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "fmondac1@uni-koeln.de", "mode": [WAC_READ]}
        ]

    def test_multiple_eppn_users(self):
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:adebbel1@uni-koeln.de", "mode": [WAC_READ]},
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "fmondac1@uni-koeln.de", "mode": [WAC_READ]},
            {"agent": "adebbel1@uni-koeln.de", "mode": [WAC_READ]},
        ]

    def test_no_foaf_person_in_output(self):
        entries = [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "mailto:user2@example.org", "mode": [WAC_READ]},
        ]
        serialized = json.dumps(serialize_permissions_data_for_acl_json(entries))
        assert "foaf:Person" not in serialized

    def test_no_internal_lacos_identifiers_in_output(self):
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:agent:someuser", "mode": [WAC_READ]},
        ]
        serialized = json.dumps(serialize_permissions_data_for_acl_json(entries))
        assert "urn:lacos:eppn:" not in serialized
        assert "urn:lacos:agent:" not in serialized

    def test_foaf_person_dropped_for_non_lacos_agents(self):
        """The foaf:Person annotation is internal-only, regardless of agent scheme."""
        entries = [{"agentClass": "foaf:Person", "agent": "mailto:user@example.org", "mode": [WAC_READ]}]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "mailto:user@example.org", "mode": [WAC_READ]}
        ]

    def test_group_entries_pass_through_unchanged(self):
        """External group representation is undecided - groups stay untouched."""
        entries = [
            {"agentClass": "foaf:Group", "agent": "urn:lacos:group:curators", "mode": [WAC_READ]},
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agentClass": "foaf:Group", "agent": "urn:lacos:group:curators", "mode": [WAC_READ]},
        ]

    def test_group_prefix_without_agent_class_passes_through(self):
        entries = [{"agent": "urn:lacos:group:curators", "mode": [WAC_READ]}]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "urn:lacos:group:curators", "mode": [WAC_READ]}
        ]

    def test_mixed_public_and_restricted(self):
        entries = [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]},
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agent": "user@example.org", "mode": [WAC_READ]},
        ]

    def test_input_not_mutated(self):
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]}
        ]
        serialize_permissions_data_for_acl_json(entries)
        assert entries == [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]}
        ]

    def test_extra_fields_and_modes_preserved(self):
        entries = [
            {
                "agentClass": "foaf:Person",
                "agent": "urn:lacos:eppn:user@example.org",
                "mode": [WAC_READ, "acl:Write"],
                "note": "custom",
            }
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "user@example.org", "mode": [WAC_READ, "acl:Write"], "note": "custom"}
        ]

    def test_non_dict_entries_pass_through(self):
        entries = [{"agentClass": WAC_AGENT, "mode": [WAC_READ]}, "not a dict", None]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            "not a dict",
            None,
        ]

    def test_entry_without_agent_passes_through(self):
        """Degenerate entries (no concrete agent) are preserved as-is."""
        entries = [{"agentClass": "foaf:Person", "mode": [WAC_READ]}]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agentClass": "foaf:Person", "mode": [WAC_READ]}
        ]

    def test_serialization_is_idempotent(self):
        """Serializing already-external data is a no-op."""
        entries = [
            {"agentClass": WAC_AGENT, "mode": [WAC_READ]},
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:user@example.org", "mode": [WAC_READ]},
            {"agentClass": "foaf:Group", "agent": "urn:lacos:group:curators", "mode": [WAC_READ]},
        ]
        once = serialize_permissions_data_for_acl_json(entries)
        assert serialize_permissions_data_for_acl_json(once) == once

    def test_unicode_eppn_serialized_bare(self):
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:eppn:müller@uni-köln.de", "mode": [WAC_READ]}
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "müller@uni-köln.de", "mode": [WAC_READ]}
        ]

    def test_native_user_urn_passes_through(self):
        """urn:lacos:user:* has no agreed external form; it must survive the
        round trip unchanged (stripping it would re-normalize differently)."""
        entries = [
            {"agentClass": "foaf:Person", "agent": "urn:lacos:user:localadmin", "mode": [WAC_READ]}
        ]
        assert serialize_permissions_data_for_acl_json(entries) == [
            {"agent": "urn:lacos:user:localadmin", "mode": [WAC_READ]}
        ]


class TestSerializePermissionsKeyOrdering:
    """Issue #138: external acl.json lists agent/agentClass before mode."""

    def test_concrete_agent_key_order_is_agent_then_mode(self):
        """Regression: internal data with mode first must serialize agent first."""
        entries = [
            {"mode": [WAC_READ], "agentClass": "foaf:Person", "agent": "urn:lacos:eppn:fmondac1@uni-koeln.de"}
        ]
        [serialized] = serialize_permissions_data_for_acl_json(entries)
        assert list(serialized.keys()) == ["agent", "mode"]

    def test_public_class_rule_key_order_is_class_then_mode(self):
        entries = [{"mode": [WAC_READ], "agentClass": WAC_AGENT}]
        [serialized] = serialize_permissions_data_for_acl_json(entries)
        assert list(serialized.keys()) == ["agentClass", "mode"]

    def test_authenticated_class_rule_key_order_is_class_then_mode(self):
        entries = [{"mode": [WAC_READ], "agentClass": WAC_AUTHENTICATED_AGENT}]
        [serialized] = serialize_permissions_data_for_acl_json(entries)
        assert list(serialized.keys()) == ["agentClass", "mode"]

    def test_extra_keys_follow_canonical_keys(self):
        entries = [{"mode": [WAC_READ], "note": "x", "agent": "urn:lacos:eppn:user@example.org"}]
        [serialized] = serialize_permissions_data_for_acl_json(entries)
        assert list(serialized.keys()) == ["agent", "mode", "note"]

    def test_rendered_json_places_agent_before_mode(self):
        entries = [
            {"mode": [WAC_READ], "agentClass": "foaf:Person", "agent": "urn:lacos:eppn:adebbel1@uni-koeln.de"}
        ]
        rendered = json.dumps(serialize_permissions_data_for_acl_json(entries))
        assert rendered.index('"agent"') < rendered.index('"mode"')
