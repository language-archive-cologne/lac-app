"""Bundle and collection utility functions."""

from collections.abc import Iterable

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Prefetch

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import ACL_LEVEL_ACADEMIC, ACL_LEVEL_PUBLIC, ACL_LEVEL_RESTRICTED
from lacos.storage.models.acl_permissions import ACLPermissions

from .resource import annotate_resource, prepare_resource_lists


BUNDLES_PER_PAGE = 10
COLLECTION_BUNDLE_ACCESS_SUMMARY_CACHE_TIMEOUT = 300
COLLECTION_BUNDLE_ACCESS_SUMMARY_CACHE_KEY_PREFIX = "explorer:collection_bundle_access_summary"


def _empty_collection_bundle_access_summary() -> dict[str, int]:
    return {
        "public": 0,
        "academic": 0,
        "restricted": 0,
        "total": 0,
    }


def _normalize_collection_summary(raw_summary: dict) -> dict[str, int]:
    return {
        "public": int(raw_summary.get("public", 0)),
        "academic": int(raw_summary.get("academic", 0)),
        "restricted": int(raw_summary.get("restricted", 0)),
        "total": int(raw_summary.get("total", 0)),
    }


def bundle_queryset_for_collection(collection, search_query=None):
    """Build a queryset for bundles belonging to a collection.

    Includes prefetching of related resources and metadata.
    Optionally filters by search_query against identifier, title, and description.
    """
    queryset = (
        BundleStructuralInfo.objects.filter(is_member_of_collection=collection)
        .select_related("bundle", "is_member_of_collection")
        .prefetch_related(
            "bundle_topics",
            "additional_metadata_files",
            Prefetch(
                "bundle__resources",
                queryset=BundleResources.objects.prefetch_related(
                    "bundle_media_resources",
                    "bundle_written_resources",
                    "bundle_other_resources",
                ),
            ),
            "bundle__general_info",
            "bundle__general_info__object_languages",
        )
    )

    if search_query:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(bundle__identifier__icontains=search_query) |
            Q(bundle__general_info__display_title__icontains=search_query) |
            Q(bundle__general_info__description__icontains=search_query)
        ).distinct()

    return queryset.order_by("bundle__identifier")


def build_bundle_context(struct_info):
    """Build context dictionary for a bundle from its structural info."""
    bundle = struct_info.bundle
    primary_resources = bundle.resources.first()

    media_resources, written_resources, other_resources = prepare_resource_lists(primary_resources)
    metadata_files = [annotate_resource(res) for res in struct_info.additional_metadata_files.all()]
    metadata_files = [res for res in metadata_files if res]
    topics = list(struct_info.bundle_topics.all())

    return {
        "structural_info": struct_info,
        "bundle": bundle,
        "primary_resources": primary_resources,
        "media_resources": media_resources,
        "written_resources": written_resources,
        "other_resources": other_resources,
        "metadata_files": metadata_files,
        "topics": topics,
    }


def paginate_bundle_contexts(collection, page_number, per_page=BUNDLES_PER_PAGE, search_query=None):
    """Paginate bundles for a collection and build context for each.

    Returns tuple of (page_obj, list of bundle contexts).
    """
    queryset = bundle_queryset_for_collection(collection, search_query=search_query)
    paginator = Paginator(queryset, per_page)

    if paginator.count == 0:
        return None, []

    page_obj = paginator.get_page(page_number)
    contexts = [build_bundle_context(struct_info) for struct_info in page_obj.object_list]
    return page_obj, contexts


def _compute_bundle_access_summary_for_collection_ids(
    collection_ids: set[str],
) -> dict[str, dict[str, int]]:
    summary_by_collection: dict[str, dict[str, int]] = {
        collection_id: _empty_collection_bundle_access_summary() for collection_id in collection_ids
    }
    bundle_pairs = list(
        BundleStructuralInfo.objects.filter(
            is_member_of_collection_id__in=collection_ids,
        ).values_list("bundle_id", "is_member_of_collection_id").distinct()
    )
    if not bundle_pairs:
        return summary_by_collection

    bundle_ids = {str(bundle_id) for bundle_id, _ in bundle_pairs}
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    bundle_levels = {
        str(object_id): level
        for object_id, level in ACLPermissions.objects.filter(
            content_type=bundle_ct,
            object_id__in=bundle_ids,
        ).values_list("object_id", "access_level")
    }

    collection_ct = ContentType.objects.get_for_model(Collection)
    collection_fallback_levels = {
        str(object_id): level
        for object_id, level in ACLPermissions.objects.filter(
            content_type=collection_ct,
            object_id__in=collection_ids,
        ).values_list("object_id", "access_level")
    }

    for bundle_id, collection_id in bundle_pairs:
        collection_key = str(collection_id)
        if collection_key not in summary_by_collection:
            continue
        counts = summary_by_collection[collection_key]
        counts["total"] += 1
        fallback_level = collection_fallback_levels.get(collection_key) or ACL_LEVEL_RESTRICTED
        level = bundle_levels.get(str(bundle_id)) or fallback_level
        if level == ACL_LEVEL_PUBLIC:
            counts["public"] += 1
        elif level == ACL_LEVEL_ACADEMIC:
            counts["academic"] += 1
        else:
            counts["restricted"] += 1

    return summary_by_collection


def summarize_bundle_access_levels_by_collection_ids(
    collection_ids: Iterable[str],
) -> dict[str, dict[str, int]]:
    """Return bundle access summaries for a set of collection ids."""
    normalized_ids = {str(collection_id) for collection_id in collection_ids if collection_id}
    if not normalized_ids:
        return {}

    cache_keys_by_collection = {
        collection_id: f"{COLLECTION_BUNDLE_ACCESS_SUMMARY_CACHE_KEY_PREFIX}:{collection_id}"
        for collection_id in normalized_ids
    }
    cached_values = cache.get_many(cache_keys_by_collection.values())
    summary_by_collection: dict[str, dict[str, int]] = {}
    missing_collection_ids: set[str] = set()

    for collection_id, cache_key in cache_keys_by_collection.items():
        cached_summary = cached_values.get(cache_key)
        if isinstance(cached_summary, dict):
            summary_by_collection[collection_id] = _normalize_collection_summary(cached_summary)
        else:
            missing_collection_ids.add(collection_id)

    if missing_collection_ids:
        computed_summaries = _compute_bundle_access_summary_for_collection_ids(missing_collection_ids)
        cache_payload = {}
        for collection_id in missing_collection_ids:
            summary = _normalize_collection_summary(
                computed_summaries.get(
                    collection_id,
                    _empty_collection_bundle_access_summary(),
                )
            )
            summary_by_collection[collection_id] = summary
            cache_payload[cache_keys_by_collection[collection_id]] = summary
        cache.set_many(cache_payload, timeout=COLLECTION_BUNDLE_ACCESS_SUMMARY_CACHE_TIMEOUT)

    return summary_by_collection


def summarize_collection_bundle_access_levels(collection) -> dict[str, int]:
    """Return aggregate bundle counts by access level for a collection."""
    if not getattr(collection, "pk", None):
        return _empty_collection_bundle_access_summary()
    summary_by_collection = summarize_bundle_access_levels_by_collection_ids([str(collection.pk)])
    return summary_by_collection.get(str(collection.pk), _empty_collection_bundle_access_summary())
