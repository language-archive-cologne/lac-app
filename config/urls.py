# ruff: noqa
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from lacos.oaipmh.views import OAIPMHOverviewView

urlpatterns = [
    path(
        "",
        RedirectView.as_view(pattern_name="explorer:collection_list"),
        name="home",
    ),
    path(
        "about/",
        TemplateView.as_view(template_name="pages/about.html"),
        name="about",
    ),
    path(
        "privacy-policy/",
        TemplateView.as_view(template_name="pages/privacy_policy.html"),
        name="privacy-policy",
    ),
    path(
        "imprint/",
        TemplateView.as_view(template_name="pages/imprint.html"),
        name="imprint",
    ),
    path(
        "user-guides/",
        TemplateView.as_view(template_name="pages/user_guides/index.html"),
        name="user-guides",
    ),
    path(
        "user-guides/mission-statement/",
        TemplateView.as_view(template_name="pages/user_guides/mission_statement.html"),
        name="user-guide-mission",
    ),
    path(
        "user-guides/privacy-policy/",
        TemplateView.as_view(template_name="pages/user_guides/privacy_policy.html"),
        name="user-guide-privacy",
    ),
    path(
        "user-guides/terms-of-use/",
        TemplateView.as_view(template_name="pages/user_guides/terms_of_use.html"),
        name="user-guide-terms",
    ),
    path(
        "user-guides/data-user-agreement/",
        TemplateView.as_view(template_name="pages/user_guides/data_user_agreement.html"),
        name="user-guide-dua",
    ),
    path(
        "user-guides/depositing-policy/",
        TemplateView.as_view(template_name="pages/user_guides/depositing_policy.html"),
        name="user-guide-depositing",
    ),
    path(
        "user-guides/depositor-guidelines/",
        TemplateView.as_view(template_name="pages/user_guides/depositor_guidelines.html"),
        name="user-guide-depositor",
    ),
    path(
        "user-guides/depositor-agreement/",
        TemplateView.as_view(template_name="pages/user_guides/depositor_agreement.html"),
        name="user-guide-agreement",
    ),
    path(
        "user-guides/submission-guidelines/",
        TemplateView.as_view(template_name="pages/user_guides/submission_guidelines.html"),
        name="user-guide-submission",
    ),
    path(
        "user-guides/metadata-template/",
        TemplateView.as_view(template_name="pages/user_guides/metadata_template.html"),
        name="user-guide-metadata",
    ),
    path(
        "user-guides/format-whitelist/",
        TemplateView.as_view(template_name="pages/user_guides/format_whitelist.html"),
        name="user-guide-formats",
    ),
    path(
        "user-guides/archive-setup/",
        TemplateView.as_view(template_name="pages/user_guides/archive_setup.html"),
        name="user-guide-archive",
    ),
    path(
        "user-guides/preservation-plan/",
        TemplateView.as_view(template_name="pages/user_guides/preservation_plan.html"),
        name="user-guide-preservation",
    ),
    path(
        "oai-pmh/",
        OAIPMHOverviewView.as_view(),
        name="oai-pmh",
    ),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("lacos.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    path("storage/", include("lacos.storage.urls", namespace="storage")),
    path("blam/", include("lacos.blam.urls")),
    path("explorer/", include("lacos.explorer.urls", namespace="explorer")),
    path("oai/", include("lacos.oaipmh.urls", namespace="oaipmh")),

    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]

if settings.SAML_LOGIN_ENABLED:
    urlpatterns.append(path("saml2/", include("djangosaml2.urls")))
if settings.DEBUG:
    # Static file serving when using Gunicorn + Uvicorn for local web socket development
    urlpatterns += staticfiles_urlpatterns()

# API URLS
urlpatterns += [
    # API base url
    path("api/", include("config.api_router")),
    # DRF auth token
    path("api/auth-token/", obtain_auth_token),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
