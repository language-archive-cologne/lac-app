from django.urls import path
from djangosaml2 import views

from lacos.users.saml_views import LacosAssertionConsumerServiceView

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="saml2_login"),
    path("acs/", LacosAssertionConsumerServiceView.as_view(), name="saml2_acs"),
    path("logout/", views.LogoutInitView.as_view(), name="saml2_logout"),
    path("ls/", views.LogoutView.as_view(), name="saml2_ls"),
    path("ls/post/", views.LogoutView.as_view(), name="saml2_ls_post"),
    path("metadata/", views.MetadataView.as_view(), name="saml2_metadata"),
]
