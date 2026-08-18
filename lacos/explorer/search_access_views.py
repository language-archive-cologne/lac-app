"""HTTP flow for obtaining an ALTCHA-backed search admission grant."""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from lacos.common.cache_rate_limit import check_rate_limit
from lacos.explorer.search_access import SEARCH_ACCESS_COOKIE_NAME
from lacos.explorer.search_access import get_search_access_service
from lacos.explorer.search_capacity import get_search_capacity_service
from lacos.explorer.search_navigation import is_search_access_target
from lacos.explorer.search_navigation import validated_search_back_url
from lacos.storage.services.altcha_service import get_altcha_service


def safe_search_target(request, candidate: str | None) -> str:
    """Return a local search-flow URL or the collection-search fallback."""
    fallback = reverse("faceted_search")
    if not candidate or not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return fallback

    if not is_search_access_target(request, candidate):
        return fallback
    return candidate


def search_access_url(request) -> str:
    target = safe_search_target(request, request.get_full_path())
    return f"{reverse('search_access')}?{urlencode({'next': target})}"


def mark_search_response_noindex(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def search_verification_required(request):
    location = search_access_url(request)
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=403)
        response.headers["HX-Redirect"] = location
        response.headers["Cache-Control"] = "no-store"
        return response
    return redirect(location)


def search_capacity_exceeded_response():
    response = HttpResponse(
        "Search is temporarily at capacity. Please retry shortly.\n",
        status=503,
        content_type="text/plain",
    )
    response.headers["Retry-After"] = str(settings.SEARCH_CAPACITY_RETRY_SECONDS)
    response.headers["Cache-Control"] = "no-store"
    return response


def search_rate_exceeded_response():
    response = HttpResponse(
        "Search requests are arriving too quickly. Please retry shortly.\n",
        status=429,
        content_type="text/plain",
    )
    response.headers["Retry-After"] = str(
        settings.SEARCH_GRANT_RATE_WINDOW_SECONDS,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


class SearchAccessRequiredMixin:
    """Reject search before transaction or queryset evaluation."""

    def dispatch(self, request, *args, **kwargs):
        enabled = settings.SEARCH_ALTCHA_ENABLED
        protected = request.method in {"GET", "HEAD"}
        if enabled and protected:
            if not request.GET:
                return mark_search_response_noindex(self.render_search_shell(request))

            access_service = get_search_access_service()
            authorization = access_service.validate(request)
            if authorization is None:
                return mark_search_response_noindex(
                    search_verification_required(request),
                )

            with get_search_capacity_service().reserve() as admitted:
                if not admitted:
                    return mark_search_response_noindex(
                        search_capacity_exceeded_response(),
                    )
                if not access_service.admit(authorization):
                    return mark_search_response_noindex(
                        search_rate_exceeded_response(),
                    )
                response = super().dispatch(request, *args, **kwargs)
                if hasattr(response, "render") and not response.is_rendered:
                    response.render()
                return mark_search_response_noindex(response)
        return mark_search_response_noindex(
            super().dispatch(request, *args, **kwargs),
        )

class SearchResultAccessRequiredMixin:
    """Require a valid search grant before rendering linked result details."""

    def dispatch(self, request, *args, **kwargs):
        protected = request.method in {"GET", "HEAD"}
        search_back = validated_search_back_url(request, request.GET.get("back"))
        if settings.SEARCH_ALTCHA_ENABLED and protected and search_back:
            access_service = get_search_access_service()
            authorization = access_service.validate(request)
            if authorization is None:
                response = search_verification_required(request)
                return mark_search_response_noindex(response)

            with get_search_capacity_service().reserve() as admitted:
                if not admitted:
                    return mark_search_response_noindex(
                        search_capacity_exceeded_response(),
                    )
                if not access_service.admit(authorization):
                    return mark_search_response_noindex(
                        search_rate_exceeded_response(),
                    )
                response = super().dispatch(request, *args, **kwargs)
                if hasattr(response, "render") and not response.is_rendered:
                    response.render()
                return mark_search_response_noindex(response)
        return super().dispatch(request, *args, **kwargs)


class SearchAccessView(View):
    """Render and verify the proof-of-work admission form."""

    template_name = "explorer/search_access.html"

    def get(self, request):
        target = safe_search_target(request, request.GET.get("next"))
        return self._render(request, target)

    def post(self, request):
        target = safe_search_target(request, request.POST.get("next"))
        if not check_rate_limit(
            request,
            "search_access_verify",
            settings.SEARCH_ALTCHA_VERIFY_RATE_LIMIT,
            settings.SEARCH_ALTCHA_VERIFY_RATE_WINDOW_SECONDS,
        ):
            response = self._render(request, target, rate_limited=True, status=429)
            response.headers["Retry-After"] = str(
                settings.SEARCH_ALTCHA_VERIFY_RATE_WINDOW_SECONDS,
            )
            return response

        payload = request.POST.get("altcha", "")
        verified, _error = get_altcha_service().verify_solution_base64(payload)
        if not verified:
            return self._render(request, target, verification_failed=True, status=403)

        grant = get_search_access_service().issue(request)
        response = redirect(target)
        response.set_cookie(
            SEARCH_ACCESS_COOKIE_NAME,
            grant.value,
            max_age=grant.max_age,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def _render(
        self,
        request,
        target,
        *,
        verification_failed=False,
        rate_limited=False,
        status=200,
    ):
        response = render(
            request,
            self.template_name,
            {
                "next": target,
                "verification_failed": verification_failed,
                "rate_limited": rate_limited,
                "search_access_minutes": max(
                    1,
                    settings.SEARCH_ALTCHA_ACCESS_TTL_SECONDS // 60,
                ),
            },
            status=status,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
