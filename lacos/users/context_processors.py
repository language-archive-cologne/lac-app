from django.conf import settings


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
        "SAML_LOGIN_ENABLED": getattr(settings, "SAML_LOGIN_ENABLED", False),
    }
