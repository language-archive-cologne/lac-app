from __future__ import annotations

from collections.abc import Iterable, Sequence

from django.db import models


def detach_parent_m2m_children(parent: models.Model, relation_name: str) -> list[int]:
    """Detach a parent's M2M children and delete any rows no longer referenced."""
    field = parent._meta.get_field(relation_name)
    through_model = field.remote_field.through
    source_field_name = field.m2m_field_name()
    target_field_name = field.m2m_reverse_field_name()

    source_field_id = f"{source_field_name}_id"
    target_field_id = f"{target_field_name}_id"

    related_ids = list(
        through_model.objects.filter(**{source_field_id: parent.pk}).values_list(
            target_field_id,
            flat=True,
        )
    )
    through_model.objects.filter(**{source_field_id: parent.pk}).delete()

    if not related_ids:
        return []

    remaining_ids = set(
        through_model.objects.filter(**{f"{target_field_id}__in": related_ids}).values_list(
            target_field_id,
            flat=True,
        )
    )
    orphan_ids = [related_id for related_id in related_ids if related_id not in remaining_ids]
    if orphan_ids:
        field.remote_field.model.objects.filter(pk__in=orphan_ids).delete()
    return related_ids


def delete_unreferenced_records(
    model: type[models.Model],
    candidate_ids: Iterable[int | None],
    relation_names: Sequence[str],
) -> None:
    """Delete records that are no longer referenced through the given relations."""
    ids = [candidate_id for candidate_id in candidate_ids if candidate_id]
    if not ids:
        return

    queryset = model.objects.filter(pk__in=ids)
    for relation_name in relation_names:
        queryset = queryset.filter(**{f"{relation_name}__isnull": True})
    queryset.delete()
