"""Explorer views package.

Re-exports all views for backwards compatibility with existing URL patterns.
"""

from .bundles import BundleDetailView, BundleJsonLdView, BundleResourcesView, BundleXmlView, ResourceAccessView, ResourceByHandleView
from .collections import CollectionDetailView, CollectionJsonLdView, CollectionListView, CollectionResourcesView, CollectionXmlView
from .bundle_faceted_search import BundleFacetedSearchView
from .faceted_search import FacetedSearchView
from .field_search import BundleFieldSearchView, FieldSearchView
from .imdi import ImdiXmlView
from .legacy import legacy_bundle_by_handle, legacy_collection_by_handle
from .utils import map_popup_view


__all__ = [
    # Collection views
    "CollectionListView",
    "CollectionDetailView",
    "CollectionJsonLdView",
    "CollectionXmlView",
    "CollectionResourcesView",
    # Faceted search
    "BundleFacetedSearchView",
    "FacetedSearchView",
    # Field search
    "BundleFieldSearchView",
    "FieldSearchView",
    # Bundle views
    "BundleDetailView",
    "BundleJsonLdView",
    "BundleResourcesView",
    "BundleXmlView",
    "ResourceAccessView",
    "ResourceByHandleView",
    "legacy_bundle_by_handle",
    "legacy_collection_by_handle",
    # IMDI views
    "ImdiXmlView",
    # Utility views
    "map_popup_view",
]
