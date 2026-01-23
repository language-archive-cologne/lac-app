from __future__ import annotations

from functools import lru_cache, wraps
import re
import uuid

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.decorators import method_decorator

ARCHIVIST_GROUP_NAME = "archivists"
COLLECTION_MANAGER_GROUP_NAME = "collection_manager"


def is_archivist(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=ARCHIVIST_GROUP_NAME).exists()


def is_collection_manager(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=COLLECTION_MANAGER_GROUP_NAME).exists()


def can_manage_collection(user, collection) -> bool:
    if is_archivist(user):
        return True
    if collection is None:
        return False
    if not is_collection_manager(user):
        return False
    from lacos.users.models import CollectionManagerAssignment
    return CollectionManagerAssignment.objects.filter(user=user, collection=collection).exists()


def can_manage_bundle(user, bundle) -> bool:
    if is_archivist(user):
        return True
    collection = _get_bundle_collection(bundle)
    return can_manage_collection(user, collection)


def _get_bundle_collection(bundle):
    if bundle is None:
        return None
    structural = getattr(bundle, "structural_info", None)
    if not structural:
        return None
    try:
        struct_info = structural.first()
    except Exception:
        return None
    if not struct_info:
        return None
    return getattr(struct_info, "is_member_of_collection", None)


def resolve_collection_from_identifier(identifier):
    if not identifier:
        return None
    from lacos.blam.models.collection.collection_repository import Collection
    collection = None
    try:
        collection_uuid = uuid.UUID(str(identifier))
    except (TypeError, ValueError):
        collection_uuid = None
    if collection_uuid:
        collection = Collection.objects.filter(pk=collection_uuid).first()
    if collection is None:
        collection = Collection.objects.filter(identifier=str(identifier)).first()
    return collection


@lru_cache(maxsize=4)
def _collection_path_regex():
    pattern = getattr(settings, "COLLECTION_PATH_PATTERN", None)
    if not pattern:
        return None
    parts = re.split(r"({[^}]+})", pattern)
    regex = ""
    seen_collection = False
    for part in parts:
        if part == "{collection_id}":
            if not seen_collection:
                regex += r"(?P<collection_id>[^/]+)"
                seen_collection = True
            else:
                regex += r"(?P=collection_id)"
            continue
        regex += re.escape(part)
    if not regex:
        return None
    return re.compile(rf"^{regex}(?:/|$)")


def extract_collection_id_from_path(path: str | None) -> str | None:
    if not path:
        return None
    normalized = path.lstrip("/")
    matcher = _collection_path_regex()
    if matcher is None:
        return None
    match = matcher.match(normalized)
    if not match:
        return None
    return match.group("collection_id")


def resolve_collection_from_path(path: str | None):
    if not path:
        return None
    candidate = extract_collection_id_from_path(path)
    if candidate:
        return resolve_collection_from_identifier(candidate)
    stripped = path.strip("/")
    if not stripped:
        return None
    collection = resolve_collection_from_identifier(stripped)
    if collection:
        return collection
    first_segment = stripped.split("/", 1)[0]
    if first_segment != stripped:
        return resolve_collection_from_identifier(first_segment)
    return None


def manager_or_archivist_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if is_archivist(request.user) or is_collection_manager(request.user):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Archivist or collection manager access required.")

    return _wrapped


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
