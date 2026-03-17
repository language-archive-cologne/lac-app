from rest_framework import status
from rest_framework.response import Response

from lacos.storage.permissions import can_manage_collection, resolve_collection_from_path


def build_legacy_upload_denied_response(
    user,
    *,
    path_hint: str | None = None,
    s3_keys: list[str] | None = None,
) -> Response | None:
    if not getattr(user, "is_authenticated", False):
        return Response(
            {"detail": "Authentication required"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    paths = []
    if path_hint is not None:
        paths.append(path_hint)
    if s3_keys:
        paths.extend(s3_keys)

    for path in paths:
        collection = resolve_collection_from_path(path)
        if can_manage_collection(user, collection):
            continue

        if collection is None:
            return Response(
                {"detail": "A collection-scoped path is required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {"detail": "Collection manager access required"},
            status=status.HTTP_403_FORBIDDEN,
        )

    return None
