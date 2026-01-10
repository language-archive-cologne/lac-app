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
    projects = models.ManyToManyField(
        'blam.ProjectInfo',
        blank=True,
        related_name='bundles',
        help_text="Projects associated with this bundle",
    )
    @property
    def base_header(self):
        """Get the bundle header"""
        return self.header.first()
    
    @property
    def get_general_info(self):
        """Get the bundle general info"""
        return self.general_info.first()
    
    @property
    def get_publication_info(self):
        """Get the bundle publication info"""
        return self.publication_info.first()
    
    @property
    def get_administrative_info(self):
        """Get the bundle administrative info"""
        return self.administrative_info.first()
    
    @property
    def get_structural_info(self):
        """Get the bundle structural info"""
        return self.structural_info.first()

    class Meta:
        verbose_name = "Bundle"
        verbose_name_plural = "Bundles"
