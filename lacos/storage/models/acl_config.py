from django.db import models


class ACLConfig(models.Model):
    """
    Singleton-ish configuration for ACL behavior, editable via UI.
    """

    enforcement_enabled = models.BooleanField(default=True)
    log_access_attempts = models.BooleanField(default=True)
    default_deny = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ACL Configuration"
        verbose_name_plural = "ACL Configuration"

    def __str__(self) -> str:
        return "ACL Configuration"

    @classmethod
    def get_solo(cls) -> "ACLConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj






