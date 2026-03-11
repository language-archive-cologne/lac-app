import uuid
from urllib.parse import unquote

from django.db import models
from django.http import Http404


def resolve_identifier(model: type[models.Model], identifier: str) -> models.Model:
    """Resolve an identifier as UUID or handle.

    Tries UUID first, then handle (identifier field), with URL decoding.
    Raises Http404 if not found.
    """
    try:
        uid = uuid.UUID(identifier)
        return model.objects.get(pk=uid)
    except (ValueError, model.DoesNotExist):
        pass

    decoded = unquote(identifier)
    try:
        return model.objects.get(identifier=decoded)
    except model.DoesNotExist:
        pass

    raise Http404(f"{model.__name__} not found: {identifier}")
