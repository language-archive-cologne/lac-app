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
from lacos.storage.utils.acl import determine_access_level, extract_read_agents


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
