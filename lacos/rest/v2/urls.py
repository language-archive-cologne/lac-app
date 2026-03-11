from django.urls import path

from lacos.rest.v2.views import auth, bundles, collections, media, resources

app_name = "v2"

urlpatterns = [
    path("collections/", collections.collection_list, name="collection-list"),
    path(
        "collections/<path:identifier>/",
        collections.collection_detail,
        name="collection-detail",
    ),
    path("bundles/", bundles.bundle_list, name="bundle-list"),
    path(
        "bundles/<path:identifier>/",
        bundles.bundle_detail,
        name="bundle-detail",
    ),
    path(
        "resources/<path:identifier>/content/",
        resources.resource_content,
        name="resource-content",
    ),
    path(
        "resources/<path:identifier>/",
        resources.resource_detail,
        name="resource-detail",
    ),
    path("media/<path:handle>/", media.media_by_handle, name="media-by-handle"),
    path("auth/validate/", auth.validate_token, name="auth-validate"),
]
