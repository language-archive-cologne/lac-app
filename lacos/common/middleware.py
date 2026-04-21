from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.utils.cache import patch_cache_control


def _origin_from_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _origins_from_settings(*setting_names: str) -> list[str]:
    origins: list[str] = []
    for setting_name in setting_names:
        origin = _origin_from_url(getattr(settings, setting_name, ""))
        if origin and origin not in origins:
            origins.append(origin)
    return origins


class SecurityHeadersMiddleware:
    """Set baseline browser security headers and disable caching for sensitive responses."""

    permissions_policy = "camera=(), geolocation=(), microphone=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def build_content_security_policy(self) -> str:
        static_origins = _origins_from_settings("STATIC_URL")
        asset_origins = _origins_from_settings(
            "STATIC_URL",
            "MEDIA_URL",
            "EXPLORER_MAP_PMTILES_URL",
            "EXPLORER_MAP_GLYPHS_URL",
            "EXPLORER_MAIN_MAP_STYLE_URL",
            "EXPLORER_MAIN_MAP_DARK_STYLE_URL",
        )

        script_src = ["'self'", "'unsafe-inline'", *static_origins]
        style_src = ["'self'", "'unsafe-inline'", *static_origins]
        img_src = ["'self'", "data:", *asset_origins]
        font_src = ["'self'", "data:", *asset_origins]
        connect_src = ["'self'", *asset_origins]
        media_src = ["'self'", *asset_origins]

        return "; ".join(
            [
                "default-src 'self'",
                "base-uri 'self'",
                "object-src 'none'",
                "frame-ancestors 'none'",
                "form-action 'self'",
                "worker-src 'self' blob:",
                f"script-src {' '.join(script_src)}",
                f"style-src {' '.join(style_src)}",
                f"img-src {' '.join(img_src)}",
                f"font-src {' '.join(font_src)}",
                f"connect-src {' '.join(connect_src)}",
                f"media-src {' '.join(media_src)}",
            ],
        )

    def __call__(self, request):
        response = self.get_response(request)

        response.headers.setdefault("Content-Security-Policy", self.build_content_security_policy())
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
