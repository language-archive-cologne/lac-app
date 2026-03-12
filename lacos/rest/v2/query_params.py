from dataclasses import dataclass

from rest_framework.exceptions import ValidationError


@dataclass(frozen=True)
class ListParams:
    ordering: str
    limit: int
    offset: int


def parse_list_params(
    query_params,
    *,
    allowed_ordering: set[str],
    default_ordering: str = "-created_at",
    max_limit: int = 100,
) -> ListParams:
    ordering = query_params.get("ordering", default_ordering)
    if ordering not in allowed_ordering:
        raise ValidationError({
            "ordering": f"Invalid ordering field. Allowed values: {', '.join(sorted(allowed_ordering))}"
        })

    raw_limit = query_params.get("limit", 10)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"limit": "Limit must be an integer"}) from exc
    if limit < 0:
        raise ValidationError({"limit": "Limit must be greater than or equal to 0"})

    raw_offset = query_params.get("offset", 0)
    try:
        offset = int(raw_offset)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"offset": "Offset must be an integer"}) from exc
    if offset < 0:
        raise ValidationError({"offset": "Offset must be greater than or equal to 0"})

    return ListParams(ordering=ordering, limit=min(limit, max_limit), offset=offset)


def build_next_url(query_params, *, limit: int, offset: int, total: int) -> str | None:
    if offset + limit >= total:
        return None

    next_params = query_params.copy()
    next_params["limit"] = limit
    next_params["offset"] = offset + limit
    return f"?{next_params.urlencode()}"
