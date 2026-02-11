"""Explorer views package.

Re-exports all views for backwards compatibility with existing URL patterns.
"""

from .bundles import BundleDetailView, BundleJsonLdView, BundleResourcesView, BundleXmlView, ResourceAccessView
from .collections import CollectionDetailView, CollectionJsonLdView, CollectionListView, CollectionResourcesView, CollectionXmlView
from .bundle_faceted_search import BundleFacetedSearchView
from .faceted_search import FacetedSearchView
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
    # Bundle views
    "BundleDetailView",
    "BundleJsonLdView",
    "BundleResourcesView",
    "BundleXmlView",
    "ResourceAccessView",
    # Utility views
    "map_popup_view",
]
