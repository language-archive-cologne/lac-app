"""Helpers for keeping BLAM creator order consistent across import and export."""

from typing import Any

from django.db.models import F
from django.db.models import QuerySet

from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_publication_info import (
    BundlePublicationInfoCreator,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfoCreator,
)

PREFETCHED_COLLECTION_CREATOR_LINKS_ATTR = "ordered_collection_creator_links"
PREFETCHED_BUNDLE_CREATOR_LINKS_ATTR = "ordered_bundle_creator_links"


def get_schema_creator_order(creator_schema: Any, fallback_index: int) -> int:
    """Return the BLAM XML creator Order value, or the element position fallback."""
    order = getattr(creator_schema, "order", None)
    if order is None:
        return fallback_index

    try:
        return int(order)
    except (TypeError, ValueError):
        return fallback_index


def order_creator_links(queryset: QuerySet) -> QuerySet:
    """Order creator through rows by explicit BLAM order, then insertion order."""
    return queryset.order_by(F("order").asc(nulls_last=True), "pk")


def ordered_collection_creator_links(
    publication_info: CollectionPublicationInfo,
) -> list[CollectionPublicationInfoCreator]:
    """Return collection creator through rows in BLAM metadata order."""
    prefetched_links = getattr(
        publication_info,
        PREFETCHED_COLLECTION_CREATOR_LINKS_ATTR,
        None,
    )
    if prefetched_links is not None:
        return list(prefetched_links)

    return list(
        order_creator_links(
            CollectionPublicationInfoCreator.objects.filter(
                collectionpublicationinfo=publication_info,
            ).select_related("collectioncreator"),
        ),
    )


def ordered_collection_creators(publication_info: CollectionPublicationInfo) -> list:
    """Return collection creators in BLAM metadata order."""
    return [
        link.collectioncreator
        for link in ordered_collection_creator_links(publication_info)
    ]


def ordered_bundle_creator_links(
    publication_info: BundlePublicationInfo,
) -> list[BundlePublicationInfoCreator]:
    """Return bundle creator through rows in BLAM metadata order."""
    prefetched_links = getattr(
        publication_info,
        PREFETCHED_BUNDLE_CREATOR_LINKS_ATTR,
        None,
    )
    if prefetched_links is not None:
        return list(prefetched_links)

    return list(
        order_creator_links(
            BundlePublicationInfoCreator.objects.filter(
                bundlepublicationinfo=publication_info,
            ).select_related("bundlecreator"),
        ),
    )


def ordered_bundle_creators(publication_info: BundlePublicationInfo) -> list:
    """Return bundle creators in BLAM metadata order."""
    return [
        link.bundlecreator
        for link in ordered_bundle_creator_links(publication_info)
    ]
