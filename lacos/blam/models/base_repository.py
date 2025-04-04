from lacos.blam.models.base_model import BaseModel
from django.db import models

class Repository(BaseModel):
    """
    Abstract base model for repositories.
    """
    identifier = models.CharField(max_length=255, null=False, unique=True)

    class Meta:
        abstract = True
