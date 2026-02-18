"""Bundle and collection utility functions."""

from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Prefetch

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
)
from lacos.storage.constants import ACL_LEVEL_ACADEMIC, ACL_LEVEL_PUBLIC, ACL_LEVEL_RESTRICTED
from lacos.storage.models.acl_permissions import ACLPermissions

from .resource import annotate_resource, prepare_resource_lists


BUNDLES_PER_PAGE = 10


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


def summarize_collection_bundle_access_levels(collection) -> dict[str, int]:
    """Return aggregate bundle counts by access level for a collection."""
    counts = {
        "public": 0,
        "academic": 0,
        "restricted": 0,
        "total": 0,
    }

    bundle_ids = [
        str(bundle_id)
        for bundle_id in bundle_queryset_for_collection(collection).values_list("bundle_id", flat=True).distinct()
    ]
    if not bundle_ids:
        return counts

    counts["total"] = len(bundle_ids)
    bundle_ct = ContentType.objects.get_for_model(Bundle)
    bundle_levels = {
        str(object_id): level
        for object_id, level in ACLPermissions.objects.filter(
            content_type=bundle_ct,
            object_id__in=bundle_ids,
        ).values_list("object_id", "access_level")
    }

    collection_ct = ContentType.objects.get_for_model(collection)
    collection_level = ACLPermissions.objects.filter(
        content_type=collection_ct,
        object_id=str(collection.pk),
    ).values_list("access_level", flat=True).first()
    fallback_level = collection_level or ACL_LEVEL_RESTRICTED

    for bundle_id in bundle_ids:
        level = bundle_levels.get(bundle_id) or fallback_level
        if level == ACL_LEVEL_PUBLIC:
            counts["public"] += 1
        elif level == ACL_LEVEL_ACADEMIC:
            counts["academic"] += 1
        else:
            counts["restricted"] += 1

    return counts
