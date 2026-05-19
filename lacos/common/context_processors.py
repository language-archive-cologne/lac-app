from django.conf import settings


def public_urls(request):
    """Expose canonical public URLs to templates."""
    return {
        "PUBLIC_BASE_URL": settings.PUBLIC_BASE_URL.rstrip("/"),
    }
