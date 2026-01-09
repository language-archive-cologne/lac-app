from django.urls import path

from . import views

app_name = "explorer"

urlpatterns = [
    path(
        "collections/",
        view=views.CollectionListView.as_view(),
        name="collection_list",
    ),
    path(
        "map-popup/",
        view=views.map_popup_view,
        name="map_popup",
    ),
    # UUID-based patterns first (more specific, won't be caught by path:handle)
    path(
        "collections/<uuid:pk>/",
        view=views.CollectionDetailView.as_view(),
        name="collection_detail",
    ),
    path(
        "bundles/<uuid:pk>/",
        view=views.BundleDetailView.as_view(),
        name="bundle_detail",
    ),
    path(
        "bundles/<uuid:pk>/resources/",
        view=views.BundleResourcesView.as_view(),
        name="bundle_resources",
    ),
    path(
        "bundles/<uuid:pk>/resources/<str:resource_id>/",
        view=views.BundleResourcesView.as_view(),
        name="resource_direct_access",
    ),
    path(
        "resource/<uuid:bundle_id>/<uuid:resource_id>/",
        view=views.ResourceAccessView.as_view(),
        name="resource_access",
    ),
    # Handle-based patterns last (path: is greedy, matches slashes)
    path(
        "collections/<path:handle>/",
        view=views.CollectionDetailView.as_view(),
        name="collection_detail_by_handle",
    ),
    path(
        "bundles/<path:handle>/resources/<str:resource_id>/",
        view=views.BundleResourcesView.as_view(),
        name="resource_direct_access_by_handle",
    ),
    path(
        "bundles/<path:handle>/resources/",
        view=views.BundleResourcesView.as_view(),
        name="bundle_resources_by_handle",
    ),
    path(
        "bundles/<path:handle>/",
        view=views.BundleDetailView.as_view(),
        name="bundle_detail_by_handle",
    ),
]
