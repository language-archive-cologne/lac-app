"""Explorer views package.

Re-exports all views for backwards compatibility with existing URL patterns.
"""

from .bundles import BundleDetailView, BundleResourcesView, ResourceAccessView
from .collections import CollectionDetailView, CollectionListView, CollectionResourcesView
from .utils import map_popup_view


__all__ = [
    # Collection views
    "CollectionListView",
    "CollectionDetailView",
    "CollectionResourcesView",
    # Bundle views
    "BundleDetailView",
    "BundleResourcesView",
    "ResourceAccessView",
    # Utility views
    "map_popup_view",
]
