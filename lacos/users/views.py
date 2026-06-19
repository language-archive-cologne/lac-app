from allauth.account.views import LoginView as AllauthLoginView
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView
from django.views.generic import RedirectView

from lacos.users.models import SamlCountry
from lacos.users.models import SamlIdp
from lacos.users.models import User

from .adapters import TRUSTED_SAML_SESSION_KEY


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"

    def get_object(self, queryset: QuerySet | None = None) -> User:
        user = super().get_object(queryset)
        request_user = self.request.user
        if request_user.is_staff or request_user == user:
            return user
        raise Http404("User not found")


user_detail_view = UserDetailView.as_view()


@require_http_methods(["GET", "POST"])
def disabled_account_management_view(request: HttpRequest) -> HttpResponse:
    raise Http404("Self-service account management is not available.")


user_update_view = disabled_account_management_view


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("home")


user_redirect_view = UserRedirectView.as_view()


@require_http_methods(["GET"])
def saml_login_view(request: HttpRequest) -> HttpResponse:
    if not settings.SAML_LOGIN_ENABLED:
        raise Http404("SAML login is not enabled.")

    request.trusted_saml_signup = True
    request.session[TRUSTED_SAML_SESSION_KEY] = True
    request.session.modified = True

    next_url = _safe_next(request, request.GET.get("next"))
    saml_login_url = _build_saml_login_url(
        next_url=next_url,
        idp=request.GET.get("idp"),
    )

    return redirect(saml_login_url)


def _safe_next(request: HttpRequest, value: str | None) -> str | None:
    if not value:
        return None
    if url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return None


def _build_saml_login_url(*, next_url: str | None = None, idp: str | None = None) -> str:
    saml_login_url = reverse("saml2_login")
    params = {}
    if next_url:
        params["next"] = next_url
    if idp:
        params["idp"] = idp
    if params:
        saml_login_url = f"{saml_login_url}?{urlencode(params)}"
    return saml_login_url


class LoginView(AllauthLoginView):
    """Redirect to SAML discovery when enabled, unless `?credentials=1` is set."""

    def dispatch(self, request, *args, **kwargs):
        if (
            settings.SAML_LOGIN_ENABLED
            and request.method == "GET"
            and request.GET.get("credentials") != "1"
        ):
            url = reverse("users:saml_discovery")
            next_url = _safe_next(request, request.GET.get("next"))
            if next_url:
                url = f"{url}?{urlencode({'next': next_url})}"
            return redirect(url)
        return super().dispatch(request, *args, **kwargs)


login_view = LoginView.as_view()


@require_http_methods(["GET"])
def saml_discovery_view(request: HttpRequest) -> HttpResponse:
    if not settings.SAML_LOGIN_ENABLED:
        raise Http404("SAML login is not enabled.")
    countries = SamlCountry.objects.filter(idps__isnull=False).distinct()
    return render(request, "users/saml_discovery.html", {
        "countries": countries,
        "next": _safe_next(request, request.GET.get("next")) or "",
        "trusted_login_url": reverse("users:saml_login"),
    })


@require_http_methods(["GET"])
def saml_discovery_idp_list(request: HttpRequest) -> HttpResponse:
    if not settings.SAML_LOGIN_ENABLED:
        raise Http404("SAML login is not enabled.")

    search = request.GET.get("search", "").strip()
    country_code = request.GET.get("country", "").strip()

    qs = SamlIdp.objects.select_related("country")
    if search:
        qs = qs.filter(display_name__icontains=search)
    if country_code:
        qs = qs.filter(country__code=country_code)
    if not search and not country_code:
        qs = qs.none()

    return render(request, "users/partials/saml_idp_list.html", {
        "idps": qs,
        "next": _safe_next(request, request.GET.get("next")) or "",
        "trusted_login_url": reverse("users:saml_login"),
    })
