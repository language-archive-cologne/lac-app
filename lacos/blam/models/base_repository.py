from django.db import models
from .base_model import BaseModel       

class Repository(BaseModel):
    """
    Abstract base model for repository information
    """
    general_info = models.ForeignKey(
        'GeneralInfo',
        on_delete=models.CASCADE,
        related_name='repositories'
    )
    publication_info = models.ForeignKey(
        'PublicationInfo',
        on_delete=models.CASCADE,
        related_name='repositories'
    )
    project_info = models.ForeignKey(
        'ProjectInfo',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_repositories'
    )
    administrative_info = models.ForeignKey(
        'AdministrativeInfo',
        on_delete=models.CASCADE,
        related_name='repositories'
    )
    structural_info = models.ForeignKey(
        'StructuralInfo',
        on_delete=models.CASCADE,
        related_name='repositories'
    )

    
    class Meta:
        abstract = True
