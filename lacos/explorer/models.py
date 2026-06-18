from django.db import models

from lacos.explorer.file_types import FILE_TYPE_LABELS


class BundleFileTypeFacet(models.Model):
    """Denormalized file-type facet values for fast collection/bundle filtering."""

    bundle = models.ForeignKey(
        "blam.Bundle",
        on_delete=models.CASCADE,
        related_name="file_type_facets",
    )
    collection = models.ForeignKey(
        "blam.Collection",
        on_delete=models.CASCADE,
        related_name="bundle_file_type_facets",
    )
    file_type = models.CharField(
        max_length=32,
        choices=[(value, label) for value, label in FILE_TYPE_LABELS.items()],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bundle", "collection", "file_type"],
                name="unique_bundle_collection_file_type",
            ),
        ]
        indexes = [
            models.Index(
                fields=["file_type", "bundle"],
                name="explorer_ftype_bundle_idx",
            ),
            models.Index(
                fields=["file_type", "collection"],
                name="explorer_ftype_collection_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bundle_id} {self.collection_id} {self.file_type}"
