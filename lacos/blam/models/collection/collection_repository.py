from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from lacos.blam.models.base_repository import Repository


class Collection(Repository):
    """
    Concrete implementation of Repository for collections.
    A collection is a curated set of bundles that form a meaningful unit.
    """
    source_version = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="BLAM schema version used during the latest import",
    )
    import_bucket = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="S3 bucket used when this collection was imported",
    )
    import_object_key = models.TextField(
        null=True,
        blank=True,
        help_text="Original S3 object key used for the collection import",
    )
    project_infos = models.ManyToManyField(
        'blam.ProjectInfo',
        blank=True,
        related_name='collections',
        help_text="Projects associated with this collection",
    )
    search_vector = SearchVectorField(null=True, blank=True)

    @property
    def base_header(self):
        """Get the collection header"""
        return self.header.first()
    
    @property
    def get_general_info(self):
        """Get the collection general info"""
        return self.general_info.first()
    
    @property
    def get_publication_info(self):
        """Get the collection publication info"""
        return self.publication_info.first()
    
    @property
    def get_administrative_info(self):
        """Get the collection administrative info"""
        return self.administrative_info.first()
    
    @property
    def get_structural_info(self):
        """Get the collection structural info"""
        return self.structural_info.first()
    
    @property
    def get_project_info(self):
        """Get the collection project info"""
        return self.project_infos.first()

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"
        indexes = [
            GinIndex(fields=['search_vector'], name='collection_search_gin_idx'),
        ]
