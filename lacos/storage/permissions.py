from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.utils.decorators import method_decorator

ARCHIVIST_GROUP_NAME = "archivists"


def is_archivist(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=ARCHIVIST_GROUP_NAME).exists()


def archivist_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_archivist(request.user):
            return HttpResponseForbidden("Archivist access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


class ArchivistRequiredMixin:
    @method_decorator(archivist_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
