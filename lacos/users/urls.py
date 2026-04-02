from django.urls import path

from .views import (
    saml_discovery_idp_list,
    saml_discovery_view,
    saml_login_view,
    user_detail_view,
    user_redirect_view,
    user_update_view,
)

app_name = "users"
urlpatterns = [
    path("login/saml/", view=saml_login_view, name="saml_login"),
    path("login/saml/discover/", view=saml_discovery_view, name="saml_discovery"),
    path("login/saml/discover/idps/", view=saml_discovery_idp_list, name="saml_discovery_idp_list"),
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<str:username>/", view=user_detail_view, name="detail"),
]
