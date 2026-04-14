# ruff: noqa
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from lacos.oaipmh.views import OAIPMHOverviewView
from lacos.sitemaps import sitemaps
from lacos.common.views import guideline_view
from lacos.explorer.views import (
    BundleFacetedSearchView,
    BundleFieldSearchView,
    CollectionListView,
    FacetedSearchView,
    FieldSearchView,
    ResourceByHandleView,
    legacy_bundle_by_handle,
    legacy_collection_by_handle,
)

urlpatterns = [
    path(
        "",
        CollectionListView.as_view(),
        name="home",
    ),
    path(
        "search/",
        FacetedSearchView.as_view(),
        name="faceted_search",
    ),
    path(
        "search/bundles/",
        BundleFacetedSearchView.as_view(),
        name="bundle_faceted_search",
    ),
    path(
        "search/fields/",
        FieldSearchView.as_view(),
        name="field_search",
    ),
    path(
        "search/bundles/fields/",
        BundleFieldSearchView.as_view(),
        name="bundle_field_search",
    ),
    # Crawler control files
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots",
    ),
    path(
        "llms.txt",
        TemplateView.as_view(template_name="llms.txt", content_type="text/plain"),
        name="llms",
    ),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
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
    # Dynamic guideline pages - checks for rendered HTML first, falls back to templates
    path("user-guides/<slug:slug>/", guideline_view, name="user-guide"),
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
    # Explorer app URLs (at root level, must come before legacy path: patterns)
    path("", include("lacos.explorer.urls", namespace="explorer")),
    # Legacy flat handle resolution (e.g. /collection/11341/..., /bundle/11341/..., /resource/11341/...)
    path(
        "collection/<path:handle_id>/",
        legacy_collection_by_handle,
        name="collection_by_handle",
    ),
    path(
        "bundle/<path:handle_id>/",
        legacy_bundle_by_handle,
        name="bundle_by_handle",
    ),
    path(
        "resource/<path:handle_id>/",
        ResourceByHandleView.as_view(),
        name="resource_by_handle",
    ),
    path("dbadmin/", include("lacos.dbadmin.urls")),
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
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema", permission_classes=[AllowAny]),
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
