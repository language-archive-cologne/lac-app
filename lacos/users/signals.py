"""
Signal registrations for the users app.

Handles:
- ACL agent URI population
- Authentication event logging (login, logout, failed login)
- Critical model deletion logging
"""

from __future__ import annotations

import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

# Import saml handlers so Django connects signal receivers on startup.
from . import saml  # noqa: F401
from .models import User
from .utils import ensure_acl_agent_uri

logger = logging.getLogger("lacos.security")


def get_client_ip(request):
    """Extract client IP address from request."""
    if request is None:
        return "unknown"
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "unknown")
    return ip


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


@receiver(post_save, sender=User)
def log_user_changes(sender, instance, created, **kwargs):
    """Log user account creation and updates."""
    if created:
        logger.info("USER_CREATED", extra={"username": instance.username, "email": instance.email})


@receiver(post_delete, sender=User)
def log_user_deletion(sender, instance, **kwargs):
    """Log user account deletion."""
    logger.warning("USER_DELETED", extra={"username": instance.username, "email": instance.email})


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log successful user login events."""
    ip_address = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "unknown")[:200] if request else "unknown"

    # Detect login method
    login_method = "unknown"
    if request and hasattr(request, "META"):
        if any(key.startswith("HTTP_") and "shib" in key.lower() for key in request.META.keys()):
            login_method = "saml"
        else:
            login_method = "regular"

    logger.info(
        "LOGIN_SUCCESS",
        extra={"user": user.username, "ip": ip_address, "method": login_method, "user_agent": user_agent},
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout events."""
    ip_address = get_client_ip(request)
    username = user.username if user else "anonymous"
    logger.info("LOGOUT", extra={"user": username, "ip": ip_address})


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request, **kwargs):
    """Log failed login attempts."""
    ip_address = get_client_ip(request)
    username = credentials.get("username", "unknown")
    user_agent = request.META.get("HTTP_USER_AGENT", "unknown")[:200] if request else "unknown"
    logger.warning(
        "LOGIN_FAILED",
        extra={"attempted_user": username, "ip": ip_address, "user_agent": user_agent},
    )

