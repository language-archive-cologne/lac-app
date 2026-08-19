"""Pure filtering, faceting, and sorting over public index records."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from django.http import QueryDict

from lacos.explorer.facets import FACET_MAX_SELECTED_VALUES
from lacos.explorer.facets import FACET_MAX_TOTAL_SELECTED_VALUES
from lacos.explorer.facets import FACET_MAX_VALUES
from lacos.explorer.facets import Facet
from lacos.explorer.facets import FacetDefinition
from lacos.explorer.facets import FacetSelectionLimitError
from lacos.explorer.facets import FacetValue
from lacos.explorer.public_search.records import PublicSearchRecord
from lacos.explorer.public_search.records import record_from_index
from lacos.explorer.text_search import expand_prefix_variants
from lacos.explorer.text_search import searchable_words

WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True)
class PublicSearchResult:
    records: list[PublicSearchRecord]
    facets: list[Facet]
    active_filters: list[dict[str, str]]
    active_search_in: list[str]
    total_count: int
    version: str
    duration_ms: float

    @property
    def server_timing(self) -> str:
        return f'public-index;dur={self.duration_ms:.1f};desc="{self.version[:12]}"'


class PublicSearchQueryEngine:
    """Evaluate one search scope without database or cache access."""

    def __init__(
        self,
        *,
        records: list[dict[str, Any]],
        definitions: list[FacetDefinition],
        version: str = "test",
        field_keys: set[str] | None = None,
    ):
        self.records = records
        self.definitions = definitions
        self.version = version
        self.field_keys = field_keys or {
            "title",
            "description",
            "keyword",
            "language",
            "location",
            "creator",
            "contributor",
            "grant_id",
            "collection",
        }

    def search(self, params: QueryDict) -> PublicSearchResult:
        started_at = perf_counter()
        selections = self._parse_selections(params)
        active_search_in = [
            value for value in params.getlist("search_in") if value in self.field_keys
        ]
        candidates = self._apply_text_search(
            self.records,
            params.get("q", ""),
            active_search_in,
        )
        facets = self._build_facets(candidates, selections)
        filtered = self._apply_facets(candidates, selections)
        ordered = self._sort(filtered, params)
        records = [record_from_index(record) for record in ordered]
        duration_ms = (perf_counter() - started_at) * 1000
        return PublicSearchResult(
            records=records,
            facets=facets,
            active_filters=self._active_filters(selections, facets),
            active_search_in=active_search_in,
            total_count=len(records),
            version=self.version,
            duration_ms=duration_ms,
        )

    def _parse_selections(self, params: QueryDict) -> dict[str, list[str]]:
        selections: dict[str, list[str]] = {}
        total = 0
        for definition in self.definitions:
            values = list(dict.fromkeys(params.getlist(definition.name)))
            values = [value for value in values if value]
            if definition.integer_values:
                values = [value for value in values if value.isdigit()]
            if definition.allowed_values is not None:
                values = [
                    value for value in values if value in definition.allowed_values
                ]
            if len(values) > FACET_MAX_SELECTED_VALUES:
                message = (
                    f"Facet '{definition.name}' exceeds the maximum of "
                    f"{FACET_MAX_SELECTED_VALUES} selections."
                )
                raise FacetSelectionLimitError(
                    message,
                )
            total += len(values)
            if total > FACET_MAX_TOTAL_SELECTED_VALUES:
                message = (
                    "The total number of facet selections exceeds the maximum "
                    f"of {FACET_MAX_TOTAL_SELECTED_VALUES}."
                )
                raise FacetSelectionLimitError(
                    message,
                )
            if values:
                selections[definition.name] = values
        return selections

    def _apply_text_search(
        self,
        records: list[dict[str, Any]],
        query: str,
        fields: list[str],
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return records
        tokens = searchable_words(query)
        if not tokens:
            return []
        return [
            record
            for record in records
            if self._record_matches_text(record, tokens, fields)
        ]

    def _record_matches_text(
        self,
        record: dict[str, Any],
        tokens: list[str],
        fields: list[str],
    ) -> bool:
        search = self._search_fields(record)
        selected_fields = fields or list(search)
        words: list[str] = []
        for field in selected_fields:
            for value in search.get(field, []):
                words.extend(WORD_PATTERN.findall(value.casefold()))
        return all(
            any(
                word.startswith(variant)
                for word in words
                for variant in expand_prefix_variants(token)
            )
            for token in tokens
        )

    @staticmethod
    def _search_fields(record: dict[str, Any]) -> dict[str, list[str]]:
        if isinstance(record.get("search"), dict):
            return record["search"]
        publication = record.get("publication", {})
        location = record.get("location", {})
        collection = record.get("collection") or {}
        return {
            "identifier": [str(record.get("identifier", ""))],
            "title": [str(record.get("title", ""))],
            "description": [str(record.get("description", ""))],
            "keyword": [str(value) for value in record.get("keywords", [])],
            "language": [
                str(value)
                for language in record.get("languages", [])
                for value in (language.get("name", ""), language.get("code", ""))
            ],
            "location": [str(value) for value in location.values()],
            "creator": [
                str(value)
                for person in publication.get("creators", [])
                for value in person.values()
            ],
            "contributor": [
                str(value)
                for person in publication.get("contributors", [])
                for value in person.values()
            ],
            "grant_id": [str(value) for value in record.get("grant_ids", [])],
            "collection": [
                str(collection.get("identifier", "")),
                str(collection.get("title", "")),
            ],
            "provider": [str(publication.get("provider", ""))],
        }

    @staticmethod
    def _apply_facets(
        records: list[dict[str, Any]],
        selections: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        selected = {name: set(values) for name, values in selections.items()}
        return [
            record
            for record in records
            if all(
                values.intersection(record.get("facets", {}).get(name, []))
                for name, values in selected.items()
            )
        ]

    def _build_facets(
        self,
        records: list[dict[str, Any]],
        selections: dict[str, list[str]],
    ) -> list[Facet]:
        facets: list[Facet] = []
        for definition in self.definitions:
            counts: Counter[str] = Counter()
            labels: dict[str, str] = {}
            for record in records:
                values = set(record.get("facets", {}).get(definition.name, []))
                if definition.allowed_values is not None:
                    values.intersection_update(definition.allowed_values)
                counts.update(values)
                labels.update(self._facet_labels(record, definition.name))
            selected = set(selections.get(definition.name, []))
            values = [
                FacetValue(
                    value=value,
                    label=(definition.label_map or {}).get(
                        value,
                        labels.get(value, value),
                    ),
                    count=count,
                    selected=value in selected,
                )
                for value, count in counts.items()
            ]
            present = {value.value for value in values}
            values.extend(
                FacetValue(value=value, label=value, count=0, selected=True)
                for value in selected - present
            )
            if definition.sort_newest_first:
                values.sort(
                    key=lambda item: (
                        not item.selected,
                        -int(item.value) if item.value.isdigit() else 0,
                    ),
                )
            else:
                values.sort(
                    key=lambda item: (
                        not item.selected,
                        -item.count,
                        item.label.casefold(),
                    ),
                )
            truncated = not definition.show_all and len(values) > FACET_MAX_VALUES
            if truncated:
                chosen = [value for value in values if value.selected]
                remaining = [value for value in values if not value.selected]
                values = chosen + remaining[: FACET_MAX_VALUES - len(chosen)]
            facets.append(
                Facet(
                    name=definition.name,
                    label=definition.label,
                    values=values,
                    truncated=truncated,
                    filterable=definition.show_all,
                ),
            )
        return facets

    @staticmethod
    def _facet_labels(record: dict[str, Any], facet_name: str) -> dict[str, str]:
        configured = record.get("facet_labels", {}).get(facet_name, {})
        if configured:
            return configured
        if facet_name == "language":
            return {
                str(language.get("code", "")): str(language.get("name", ""))
                for language in record.get("languages", [])
            }
        if facet_name == "collection" and record.get("collection"):
            collection = record["collection"]
            return {
                str(collection.get("identifier", "")): str(
                    collection.get("title", ""),
                ),
            }
        return {}

    @staticmethod
    def _active_filters(
        selections: dict[str, list[str]],
        facets: list[Facet],
    ) -> list[dict[str, str]]:
        facets_by_name = {facet.name: facet for facet in facets}
        active: list[dict[str, str]] = []
        for facet_name, values in selections.items():
            facet = facets_by_name[facet_name]
            labels = {value.value: value.label for value in facet.values}
            active.extend(
                {
                    "facet_name": facet_name,
                    "facet_label": facet.label,
                    "value": value,
                    "label": labels.get(value, value),
                }
                for value in values
            )
        return active

    @staticmethod
    def _sort(
        records: list[dict[str, Any]],
        params: QueryDict,
    ) -> list[dict[str, Any]]:
        sort_key = params.get("sort", "name")
        reverse = params.get("order", "asc") == "desc"
        ordered = sorted(
            records,
            key=lambda record: (
                str(record.get("title", "")).casefold(),
                str(record.get("identifier", "")),
            ),
        )

        def primary(record):
            if sort_key == "language":
                names = [
                    str(language.get("name", "")).casefold()
                    for language in record.get("languages", [])
                ]
                return min(names, default="")
            if sort_key == "collection":
                collection = record.get("collection") or {}
                return str(collection.get("identifier", "")).casefold()
            if sort_key == "bundles":
                return int(record.get("bundles_count", 0))
            return str(record.get("title", "")).casefold()

        ordered.sort(key=primary, reverse=reverse)
        return ordered
