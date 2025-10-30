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
    acl_agent_uri = models.URLField(
        _("ACL agent URI"),
        blank=True,
        null=True,
        max_length=1024,
        help_text=_("URI used when matching foaf:Person ACL rules."),
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
    acl_agent_uri = models.URLField(
        _("ACL agent URI"),
        blank=True,
        null=True,
        max_length=1024,
        help_text=_("URI used when matching foaf:Group ACL rules."),
    )

    class Meta:
        verbose_name = _("Group ACL profile")
        verbose_name_plural = _("Group ACL profiles")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.group.name} ACL profile"
