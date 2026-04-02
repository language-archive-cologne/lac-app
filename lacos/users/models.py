from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.db.models import CharField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Default custom user model for Language Archive Cologne.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    saml_persistent_id = models.CharField(
        _("SAML persistent identifier"),
        blank=True,
        null=True,
        unique=True,
        max_length=255,
        help_text=_(
            "Immutable identifier supplied by the Identity Provider for returning SAML users.",
        ),
    )
    acl_agent_uri = models.CharField(
        _("ACL agent URI"),
        blank=True,
        null=True,
        max_length=1024,
        help_text=_("URI used when matching foaf:Person ACL rules (e.g., urn:lacos:user:username)."),
    )

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})


class GroupACL(models.Model):
    """
    Stores optional ACL agent URIs for Django auth groups.

    When present, the URI is matched against foaf:Group entries in ACL rules.
    """

    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="acl_profile",
    )
    acl_agent_uri = models.CharField(
        _("ACL agent URI"),
        blank=True,
        null=True,
        max_length=1024,
        help_text=_("URI used when matching foaf:Group ACL rules (e.g., urn:lacos:group:groupname)."),
    )

    class Meta:
        verbose_name = _("Group ACL profile")
        verbose_name_plural = _("Group ACL profiles")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.group.name} ACL profile"


class SamlCountry(models.Model):
    code = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = _("SAML country")
        verbose_name_plural = _("SAML countries")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class SamlIdp(models.Model):
    entity_id = models.TextField(unique=True)
    display_name = models.CharField(max_length=512)
    logo = models.TextField(blank=True, default="")
    country = models.ForeignKey(
        SamlCountry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idps",
    )

    class Meta:
        verbose_name = _("SAML identity provider")
        verbose_name_plural = _("SAML identity providers")
        ordering = ["display_name"]
        indexes = [
            models.Index(fields=["display_name"]),
            models.Index(fields=["country"]),
        ]

    def __str__(self) -> str:
        return self.display_name


class CollectionManagerAssignment(models.Model):
    """
    Assigns a user to manage one or more collections.

    Requires the user to also be in the collection_manager group for access checks.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="collection_manager_assignments",
    )
    collection = models.ForeignKey(
        "blam.Collection",
        on_delete=models.CASCADE,
        related_name="collection_manager_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Collection manager assignment")
        verbose_name_plural = _("Collection manager assignments")
        unique_together = ("user", "collection")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.user} -> {self.collection}"
