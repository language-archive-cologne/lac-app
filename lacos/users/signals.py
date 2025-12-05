"""
Signal registrations for the users app.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

# Import saml handlers so Django connects signal receivers on startup.
from . import saml  # noqa: F401
from .models import User
from .utils import ensure_acl_agent_uri


@receiver(post_save, sender=User)
def auto_populate_acl_agent_uri(sender, instance, created, **kwargs):
    """
    Auto-populate acl_agent_uri for new users if not already set.

    For Shibboleth users, this is handled in saml.py before save.
    This handles native Django users created via other means.
    """
    if not instance.acl_agent_uri and instance.username:
        # Only set for non-SAML users (SAML users get urn:eppn: format in saml.py)
        if not instance.saml_persistent_id:
            instance.acl_agent_uri = f"urn:lacos:user:{instance.username}"
            # Use update to avoid recursion
            User.objects.filter(pk=instance.pk).update(acl_agent_uri=instance.acl_agent_uri)

