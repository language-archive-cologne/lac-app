from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from lacos.blam.models.base_repository import Repository


class Bundle(Repository):
    """
    Concrete implementation of Repository for bundles.
    A bundle is a coherent set of data and metadata files that form a meaningful unit.
    It is a member of a collection.

    """
    import_bucket = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="S3 bucket used when this bundle was imported",
    )
    import_object_key = models.TextField(
        null=True,
        blank=True,
        help_text="Original S3 object key used for the bundle import",
    )
    import_etag = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="S3 ETag from last successful reindex",
    )
    projects = models.ManyToManyField(
        'blam.ProjectInfo',
        blank=True,
        related_name='bundles',
        help_text="Projects associated with this bundle",
    )
    search_vector = SearchVectorField(null=True, blank=True)

    @property
    def base_header(self):
        """Get the bundle header"""
        return self._first_related("header")
    
    @property
    def get_general_info(self):
        """Get the bundle general info"""
        return self._first_related("general_info")
    
    @property
    def get_publication_info(self):
        """Get the bundle publication info"""
        return self._first_related("publication_info")
    
    @property
    def get_administrative_info(self):
        """Get the bundle administrative info"""
        return self._first_related("administrative_info")
    
    @property
    def get_structural_info(self):
        """Get the bundle structural info"""
        return self._first_related("structural_info")

    class Meta:
        verbose_name = "Bundle"
        verbose_name_plural = "Bundles"
        indexes = [
            GinIndex(fields=['search_vector'], name='bundle_search_gin_idx'),
        ]
