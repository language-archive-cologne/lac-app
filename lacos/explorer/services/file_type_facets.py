from django.db import transaction

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.explorer.facets import FacetService
from lacos.explorer.file_types import file_type_for_resource
from lacos.explorer.models import BundleFileTypeFacet


@transaction.atomic
def refresh_bundle_file_type_facets(bundle: Bundle) -> int:
    """Rebuild file-type facet rows for a bundle from its stored resources."""
    BundleFileTypeFacet.objects.filter(bundle=bundle).delete()

    collection_ids = list(
        BundleStructuralInfo.objects.filter(bundle=bundle)
        .values_list("is_member_of_collection_id", flat=True)
        .distinct(),
    )
    file_types = _file_types_for_bundle(bundle)
    if not collection_ids or not file_types:
        FacetService.invalidate_cache()
        return 0

    rows = [
        BundleFileTypeFacet(
            bundle=bundle,
            collection_id=collection_id,
            file_type=file_type,
        )
        for collection_id in collection_ids
        for file_type in sorted(file_types)
    ]
    BundleFileTypeFacet.objects.bulk_create(rows, ignore_conflicts=True)
    FacetService.invalidate_cache()
    return len(rows)


def _file_types_for_bundle(bundle: Bundle) -> set[str]:
    file_types: set[str] = set()
    for resources in (
        BundleResources.objects.filter(bundle=bundle)
        .prefetch_related(
            "bundle_media_resources",
            "bundle_written_resources",
            "bundle_other_resources",
        )
    ):
        for resource in resources.bundle_media_resources.all():
            _add_file_type(file_types, resource)
        for resource in resources.bundle_written_resources.all():
            _add_file_type(file_types, resource)
        for resource in resources.bundle_other_resources.all():
            _add_file_type(file_types, resource)

    structural_infos = (
        BundleStructuralInfo.objects.filter(bundle=bundle).prefetch_related(
            "additional_metadata_files",
        )
    )
    for structural_info in structural_infos:
        for metadata_file in structural_info.additional_metadata_files.all():
            _add_file_type(file_types, metadata_file)

    return file_types


def _add_file_type(file_types: set[str], resource) -> None:
    file_type = _file_type_for_model(resource)
    if file_type:
        file_types.add(file_type)


def _file_type_for_model(resource) -> str | None:
    return file_type_for_resource(
        getattr(resource, "mime_type", None),
        getattr(resource, "file_name", None),
    )
