"""Lookup utilities for resolving objects by UUID or handle."""

from urllib.parse import unquote

from django.http import Http404
from django.shortcuts import get_object_or_404


HDL_RESOLVER_PREFIXES = (
    "https://hdl.handle.net/",
    "http://hdl.handle.net/",
)


def hdl_pid_candidates(value):
    """Return possible stored PID forms for a URL handle path or PID value."""
    decoded = unquote(str(value or "")).strip().rstrip("/")
    if decoded.startswith("ID_"):
        decoded = decoded[3:]
    if not decoded:
        return []

    clean_handle = decoded
    if clean_handle.startswith("hdl:"):
        clean_handle = clean_handle[4:]
    else:
        for prefix in HDL_RESOLVER_PREFIXES:
            if clean_handle.startswith(prefix):
                clean_handle = clean_handle[len(prefix):]
                break

    candidates = []

    def add(candidate):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(f"hdl:{clean_handle}")
    add(f"https://hdl.handle.net/{clean_handle}")
    add(f"http://hdl.handle.net/{clean_handle}")
    add(decoded)
    return candidates


def get_object_by_pk_or_handle(model, pk=None, handle=None):
    """
    Get an object by either its primary key (UUID) or its identifier (handle).

    Args:
        model: The Django model class to query
        pk: The UUID primary key (optional)
        handle: The identifier/handle string (optional)

    Returns:
        The model instance

    Raises:
        Http404: If no object is found
    """
    if pk is not None:
        return get_object_or_404(model, pk=pk)

    if handle is not None:
        # Try as-is first, then with hdl: prefix (URLs no longer include hdl:)
        obj = model.objects.filter(identifier=handle).first()
        if obj is None and not handle.startswith('hdl:'):
            obj = model.objects.filter(identifier=f"hdl:{handle}").first()
        if obj is None:
            raise Http404(f"{model.__name__} with handle '{handle}' not found")
        return obj

    raise Http404(f"No {model.__name__} identifier provided")


class HandleLookupMixin:
    """
    Mixin for DetailView subclasses to support lookup by handle (identifier).

    The URL can provide either:
    - pk: UUID primary key (standard Django behavior)
    - handle: identifier field value
    """

    def get_object(self, queryset=None):
        """Get object by pk or handle."""
        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs.get(self.pk_url_kwarg)
        handle = self.kwargs.get('handle')

        if pk is not None:
            queryset = queryset.filter(pk=pk)
        elif handle is not None:
            # Try as-is first, then with hdl: prefix (URLs no longer include hdl:)
            if not handle.startswith('hdl:') and not queryset.filter(identifier=handle).exists():
                handle = f"hdl:{handle}"
            queryset = queryset.filter(identifier=handle)
        else:
            raise AttributeError(
                f"{self.__class__.__name__} must be called with either pk or handle"
            )

        try:
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(
                f"No {queryset.model._meta.verbose_name} found matching the query"
            )

        return obj
