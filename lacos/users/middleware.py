from __future__ import annotations

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect

from lacos.users.security import (
    build_mfa_redirect_url,
    privileged_path_prefixes,
    user_has_mfa_authenticator,
    user_requires_mfa,
)


class PrivilegedMFAEnforcementMiddleware:
    """Require privileged users to enroll an MFA authenticator before sensitive access."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user_requires_mfa(user) and not user_has_mfa_authenticator(user):
            if request.path.startswith(privileged_path_prefixes()):
                redirect_url = build_mfa_redirect_url(request)
                if request.path.startswith("/api/"):
                    return JsonResponse(
                        {"detail": "MFA enrollment is required for privileged access."},
                        status=403,
                    )
                if request.headers.get("HX-Request") == "true":
                    response = HttpResponseForbidden("MFA enrollment is required for privileged access.")
                    response["HX-Redirect"] = redirect_url
                    return response
                return redirect(redirect_url)

        return self.get_response(request)
