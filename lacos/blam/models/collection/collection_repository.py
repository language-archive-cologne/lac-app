from django.db import models
from lacos.blam.models.base_repository import Repository


class Collection(Repository):
    """
    Concrete implementation of Repository for collections.
    A collection is a curated set of bundles that form a meaningful unit.
    """
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
        return self.project_info.first()

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"

