"""
Utility functions for user management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User


def generate_acl_agent_uri(user: User) -> str | None:
    """
    Generate an ACL agent URI for a user based on their authentication type.

    All URIs are prefixed with urn:lacos: to clearly identify them as
    LACOS-generated and avoid conflicts with external URIs.

    Shibboleth users (identified by saml_persistent_id):
        urn:lacos:eppn:<username>  (username is typically the eduPersonPrincipalName)

    Native Django users:
        urn:lacos:user:<username>

    Returns None if the user has no username.
    """
    if not user.username:
        return None

    # Shibboleth users have saml_persistent_id set
    if user.saml_persistent_id:
        return f"urn:lacos:eppn:{user.username}"

    # Native Django users
    return f"urn:lacos:user:{user.username}"


def ensure_acl_agent_uri(user: User, save: bool = False) -> bool:
    """
    Ensure a user has an acl_agent_uri set. If not, generate one.

    Args:
        user: The user instance
        save: If True, save the user after setting the URI

    Returns:
        True if the URI was generated/updated, False if already set
    """
    if user.acl_agent_uri:
        return False

    uri = generate_acl_agent_uri(user)
    if uri:
        user.acl_agent_uri = uri
        if save:
            user.save(update_fields=["acl_agent_uri"])
        return True

    return False
