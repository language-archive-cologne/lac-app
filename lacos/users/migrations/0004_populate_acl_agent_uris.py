"""
Data migration to populate acl_agent_uri for existing users.
"""

from django.db import migrations


def populate_acl_agent_uris(apps, schema_editor):
    """
    Populate acl_agent_uri for users that don't have one set.

    All URIs are prefixed with urn:lacos: to clearly identify them as
    LACOS-generated and avoid conflicts with external URIs.

    - Shibboleth users (with saml_persistent_id): urn:lacos:eppn:<username>
    - Native users: urn:lacos:user:<username>
    """
    User = apps.get_model("users", "User")

    # Update Shibboleth users
    shibboleth_users = User.objects.filter(
        acl_agent_uri__isnull=True,
        saml_persistent_id__isnull=False,
        username__isnull=False,
    ).exclude(username="")

    for user in shibboleth_users:
        user.acl_agent_uri = f"urn:lacos:eppn:{user.username}"
        user.save(update_fields=["acl_agent_uri"])

    # Also handle empty string
    shibboleth_users_empty = User.objects.filter(
        acl_agent_uri="",
        saml_persistent_id__isnull=False,
        username__isnull=False,
    ).exclude(username="")

    for user in shibboleth_users_empty:
        user.acl_agent_uri = f"urn:lacos:eppn:{user.username}"
        user.save(update_fields=["acl_agent_uri"])

    # Update native users
    native_users = User.objects.filter(
        acl_agent_uri__isnull=True,
        saml_persistent_id__isnull=True,
        username__isnull=False,
    ).exclude(username="")

    for user in native_users:
        user.acl_agent_uri = f"urn:lacos:user:{user.username}"
        user.save(update_fields=["acl_agent_uri"])

    # Also handle empty string
    native_users_empty = User.objects.filter(
        acl_agent_uri="",
        saml_persistent_id__isnull=True,
        username__isnull=False,
    ).exclude(username="")

    for user in native_users_empty:
        user.acl_agent_uri = f"urn:lacos:user:{user.username}"
        user.save(update_fields=["acl_agent_uri"])


def reverse_populate(apps, schema_editor):
    """
    Reverse migration - clear auto-generated URIs.
    Only clears URIs that match the expected urn:lacos: pattern.
    """
    User = apps.get_model("users", "User")

    # Clear all LACOS-generated URIs
    User.objects.filter(acl_agent_uri__startswith="urn:lacos:").update(acl_agent_uri=None)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_saml_persistent_id"),
    ]

    operations = [
        migrations.RunPython(populate_acl_agent_uris, reverse_populate),
    ]
