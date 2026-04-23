import logging
from collections.abc import Callable
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, OuterRef, Q, Subquery
from django.db.models.functions import Cast

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import (
    ACL_LEVEL_ACADEMIC,
    ACL_LEVEL_PUBLIC,
    ACL_LEVEL_RESTRICTED,
)
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.acl_service import ACLService


logger = logging.getLogger(__name__)

ACL_COLLECTION_BUNDLE_LOAD_MODE_MISSING = "missing"
ACL_COLLECTION_BUNDLE_LOAD_MODE_ALL = "all"
VALID_COLLECTION_BUNDLE_LOAD_MODES = {
    ACL_COLLECTION_BUNDLE_LOAD_MODE_MISSING,
    ACL_COLLECTION_BUNDLE_LOAD_MODE_ALL,
}
PRESENT_BUNDLE_ACCESS_LEVELS = (
    ACL_LEVEL_PUBLIC,
    ACL_LEVEL_ACADEMIC,
    ACL_LEVEL_RESTRICTED,
)


def get_collection_bundle_queryset(collection: Collection, mode: str):
    """Return the bundle queryset targeted by the selected bulk-load mode."""
    if mode not in VALID_COLLECTION_BUNDLE_LOAD_MODES:
        raise ValueError(f"Invalid mode: {mode}")

    queryset = (
        Bundle.objects.filter(structural_info__is_member_of_collection=collection)
        .annotate(pk_str=Cast("pk", output_field=CharField()))
        .distinct()
        .order_by("identifier")
    )

    if mode == ACL_COLLECTION_BUNDLE_LOAD_MODE_ALL:
        return queryset

    bundle_ct = ContentType.objects.get_for_model(Bundle)
    permission_qs = ACLPermissions.objects.filter(
        content_type=bundle_ct,
        object_id=OuterRef("pk_str"),
    )

    return queryset.annotate(
        access_level=Subquery(permission_qs.values("access_level")[:1]),
    ).filter(
        Q(access_level__isnull=True)
        | ~Q(access_level__in=PRESENT_BUNDLE_ACCESS_LEVELS)
    )


def load_collection_bundle_acls(
    collection: Collection,
    mode: str,
    *,
    acl_service: ACLService | None = None,
    progress_callback: Callable[[int, int, Bundle], None] | None = None,
) -> dict[str, Any]:
    """Load bundle ACLs for one collection and return a summary."""
    service = acl_service or ACLService(skip_bucket_check=True)
    bundles = list(get_collection_bundle_queryset(collection, mode))

    summary: dict[str, Any] = {
        "collection_id": str(collection.pk),
        "collection_identifier": getattr(collection, "identifier", str(collection.pk)),
        "mode": mode,
        "total": len(bundles),
        "loaded": 0,
        "errors": 0,
        "failed_bundles": [],
    }

    total = len(bundles)
    for index, bundle in enumerate(bundles, start=1):
        if progress_callback:
            progress_callback(index, total, bundle)

        try:
            result = service.load_bundle(bundle, force_refresh=True)
        except Exception:
            logger.exception(
                "Failed loading bundle ACL",
                extra={
                    "collection_id": str(collection.pk),
                    "bundle_id": str(bundle.pk),
                    "mode": mode,
                },
            )
            summary["errors"] += 1
            summary["failed_bundles"].append(bundle.identifier)
            continue

        if result.success:
            summary["loaded"] += 1
            continue

        summary["errors"] += 1
        summary["failed_bundles"].append(bundle.identifier)

    return summary
