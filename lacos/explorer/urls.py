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
]
