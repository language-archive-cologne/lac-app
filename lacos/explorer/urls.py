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
        "imdi/xml/",
        view=views.ImdiXmlView.as_view(),
        name="imdi_xml",
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
        "resource/<uuid:bundle_id>/<uuid:resource_id>/",
        view=views.ResourceAccessView.as_view(),
        name="resource_access",
    ),
    # Handle-based patterns last (path: is greedy, matches slashes)
    path(
        "bundles/<path:handle>/resources/<path:resource_pid>/",
        view=views.ResourceAccessView.as_view(),
        name="resource_access_by_handle",
    ),
    path(
        "collections/<path:handle>/resources/<path:resource_id>/",
        view=views.CollectionResourcesView.as_view(),
        name="collection_resource_by_handle",
    ),
    path(
        "collections/<path:handle>/metadata.jsonld",
        view=views.CollectionJsonLdView.as_view(),
        name="collection_jsonld_by_handle",
    ),
    path(
        "collections/<path:handle>/metadata.xml",
        view=views.CollectionXmlView.as_view(),
        name="collection_xml_by_handle",
    ),
    path(
        "collections/<path:handle>/",
        view=views.CollectionDetailView.as_view(),
        name="collection_detail_by_handle",
    ),
    path(
        "bundles/<path:handle>/metadata.jsonld",
        view=views.BundleJsonLdView.as_view(),
        name="bundle_jsonld_by_handle",
    ),
    path(
        "bundles/<path:handle>/metadata.xml",
        view=views.BundleXmlView.as_view(),
        name="bundle_xml_by_handle",
    ),
    path(
        "bundles/<path:handle>/",
        view=views.BundleDetailView.as_view(),
        name="bundle_detail_by_handle",
    ),
]
