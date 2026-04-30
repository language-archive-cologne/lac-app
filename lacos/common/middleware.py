from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.utils.cache import patch_cache_control

from lacos.common.services.csp import (
    InlineCspHashes,
    collect_form_action_origins,
    collect_inline_csp_hashes,
)


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


def _origins_from_values(values: list[str] | tuple[str, ...]) -> list[str]:
    origins: list[str] = []
    for value in values:
        origin = _origin_from_url(value)
        if origin and origin not in origins:
            origins.append(origin)
    return origins


class SecurityHeadersMiddleware:
    """Set baseline browser security headers and disable caching for sensitive responses."""

    permissions_policy = "camera=(), geolocation=(), microphone=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def build_content_security_policy(
        self,
        *,
        inline_hashes: InlineCspHashes | None = None,
        form_action_origins: tuple[str, ...] = (),
    ) -> str:
        inline_hashes = inline_hashes or InlineCspHashes()
        static_origins = _origins_from_settings("STATIC_URL")
        asset_origins = _origins_from_settings(
            "STATIC_URL",
            "MEDIA_URL",
            "AWS_S3_BROWSER_ENDPOINT_URL",
            "AWS_S3_ENDPOINT_URL",
            "EXPLORER_MAP_PMTILES_URL",
            "EXPLORER_MAP_GLYPHS_URL",
            "EXPLORER_MAIN_MAP_STYLE_URL",
            "EXPLORER_MAIN_MAP_DARK_STYLE_URL",
        )
        asset_origins.extend(
            origin
            for origin in _origins_from_values(
                getattr(settings, "CSP_EXTRA_ASSET_ORIGINS", [])
            )
            if origin not in asset_origins
        )
        saml_form_origins = _origins_from_settings(
            "SAML_METADATA_REFRESH_URL",
            "SAML2_DISCO_URL",
        )
        saml_form_origins.extend(
            origin
            for origin in _origins_from_values(
                getattr(settings, "SAML_FORM_ACTION_ORIGINS", [])
            )
            if origin not in saml_form_origins
        )

        script_src = ["'self'", *static_origins]
        style_src = ["'self'", "'unsafe-inline'", *static_origins]
        style_elem = ["'self'", "'unsafe-inline'", *static_origins]
        style_attr = ["'unsafe-inline'"]
        img_src = ["'self'", "data:", *asset_origins]
        font_src = ["'self'", "data:", *asset_origins]
        connect_src = ["'self'", *asset_origins]
        media_src = ["'self'", *asset_origins]
        frame_src = ["'self'", *asset_origins]
        form_action = ["'self'", *saml_form_origins]
        form_action.extend(
            origin for origin in form_action_origins if origin not in form_action
        )

        if inline_hashes.script_hashes:
            if inline_hashes.has_script_attribute_hashes:
                script_src.append("'unsafe-hashes'")
            script_src.extend(inline_hashes.script_hashes)

        if inline_hashes.style_hashes:
            if inline_hashes.has_style_attribute_hashes:
                style_src.append("'unsafe-hashes'")
            style_src.extend(inline_hashes.style_hashes)

        return "; ".join(
            [
                "default-src 'self'",
                "base-uri 'self'",
                "object-src 'none'",
                "frame-ancestors 'none'",
                f"form-action {' '.join(form_action)}",
                "worker-src 'self' blob:",
                f"frame-src {' '.join(frame_src)}",
                f"script-src {' '.join(script_src)}",
                f"style-src {' '.join(style_src)}",
                f"style-src-elem {' '.join(style_elem)}",
                f"style-src-attr {' '.join(style_attr)}",
                f"img-src {' '.join(img_src)}",
                f"font-src {' '.join(font_src)}",
                f"connect-src {' '.join(connect_src)}",
                f"media-src {' '.join(media_src)}",
            ],
        )

    def _response_document(self, response) -> str:
        if getattr(response, "streaming", False) or not hasattr(response, "content"):
            return ""

        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith(("text/html", "application/xhtml+xml")):
            return ""

        encoding = getattr(response, "charset", "utf-8") or "utf-8"
        return response.content.decode(encoding, errors="ignore")

    def __call__(self, request):
        response = self.get_response(request)
        document = self._response_document(response)
        inline_hashes = collect_inline_csp_hashes(document) if document else InlineCspHashes()
        form_action_origins = collect_form_action_origins(document) if document else ()

        response.headers.setdefault(
            "Content-Security-Policy",
            self.build_content_security_policy(
                inline_hashes=inline_hashes,
                form_action_origins=form_action_origins,
            ),
        )
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
