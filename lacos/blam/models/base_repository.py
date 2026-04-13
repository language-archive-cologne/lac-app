from django.db import models

from lacos.blam.models.base_model import BaseModel


class Repository(BaseModel):
    """
    Abstract base model for repositories.
    """
    identifier = models.CharField(max_length=255, null=False, unique=True)

    def _first_related(self, related_name: str):
        """Return the first related object, using the prefetch cache when available."""
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache and related_name in cache:
            return next(iter(cache[related_name]), None)
        return getattr(self, related_name).first()

    @property
    def handle_path(self):
        """Return identifier without hdl: prefix, for use in URLs."""
        if self.identifier and self.identifier.startswith('hdl:'):
            return self.identifier[4:]
        return self.identifier or ''

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.identifier
