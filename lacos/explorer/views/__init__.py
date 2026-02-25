"""Explorer views package.

Re-exports all views for backwards compatibility with existing URL patterns.
"""

from .bundles import BundleDetailView, BundleJsonLdView, BundleResourcesView, BundleXmlView, ResourceAccessView
from .collections import CollectionDetailView, CollectionJsonLdView, CollectionListView, CollectionResourcesView, CollectionXmlView
from .bundle_faceted_search import BundleFacetedSearchView
from .faceted_search import FacetedSearchView
from .field_search import BundleFieldSearchView, FieldSearchView
from .imdi import ImdiBrowserView, ImdiDetailView, ImdiTreeChildrenView
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
    # IMDI views
    "ImdiBrowserView",
    "ImdiTreeChildrenView",
    "ImdiDetailView",
    # Utility views
    "map_popup_view",
]
