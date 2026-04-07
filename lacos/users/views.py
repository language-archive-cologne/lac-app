from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView

from lacos.users.models import SamlCountry, SamlIdp, User
from .adapters import TRUSTED_SAML_SESSION_KEY


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None=None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


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

    next_url = request.GET.get("next")
    saml_login_url = reverse("saml2_login")
    if next_url:
        saml_login_url = f"{saml_login_url}?{urlencode({'next': next_url})}"

    return redirect(saml_login_url)


@require_http_methods(["GET"])
def saml_discovery_view(request: HttpRequest) -> HttpResponse:
    if not settings.SAML_LOGIN_ENABLED:
        raise Http404("SAML login is not enabled.")
    countries = SamlCountry.objects.filter(idps__isnull=False).distinct()
    return render(request, "users/saml_discovery.html", {
        "countries": countries,
        "next": request.GET.get("next", ""),
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
        "next": request.GET.get("next", ""),
    })
