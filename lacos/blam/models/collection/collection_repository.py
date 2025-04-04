from django.db import models
from lacos.blam.models.base_model import BaseModel
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
from lacos.blam.models.base_project_info import ProjectInfo


class Collection(BaseModel):
    """
    Concrete implementation of Repository for collections.
    A collection is a curated set of bundles that form a meaningful unit.
    """

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"

