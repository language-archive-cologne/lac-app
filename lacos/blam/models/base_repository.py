from django.db import models
from lacos.blam.models.base_model import BaseModel       

class Repository(BaseModel):
    """
    Abstract base model for repository information
    
    This class defines the common structure for repositories (Bundles, Collections, etc.)
    with relationships to various types of information. Concrete subclasses should
    override these fields with specific implementations.
    """
    general_info = models.ForeignKey(
        'GeneralInfo',
        on_delete=models.CASCADE,
        related_name='base_general'
    )
    publication_info = models.ForeignKey(
        'PublicationInfo',
        on_delete=models.CASCADE,
        related_name='base_publication'
    )
    project_info = models.ForeignKey(
        'ProjectInfo',
        on_delete=models.CASCADE,
        related_name='base_project'
    )
    administrative_info = models.ForeignKey(
        'AdministrativeInfo',
        on_delete=models.CASCADE,
        related_name='base_administrative'
    )
    structural_info = models.ForeignKey(
        'StructuralInfo',
        on_delete=models.CASCADE,
        related_name='base_structural'
    )

    
    class Meta:
        abstract = True
