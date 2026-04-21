from __future__ import annotations

from django.utils.cache import patch_cache_control


class SecurityHeadersMiddleware:
    """Set baseline browser security headers and disable caching for sensitive responses."""

    content_security_policy = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https:; "
        "connect-src 'self' https:; "
        "media-src 'self' https:;"
    )

    permissions_policy = "camera=(), geolocation=(), microphone=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response.headers.setdefault("Content-Security-Policy", self.content_security_policy)
        response.headers.setdefault("Permissions-Policy", self.permissions_policy)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Referrer-Policy", "same-origin")

        is_authenticated = bool(getattr(request, "user", None) and request.user.is_authenticated)
        if request.path.startswith("/api/v2/auth/") or (
            is_authenticated and request.headers.get("HX-Request") == "true"
        ):
            patch_cache_control(
                response,
                private=True,
                no_cache=True,
                no_store=True,
                must_revalidate=True,
            )

        return response
