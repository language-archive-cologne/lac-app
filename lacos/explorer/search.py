from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import re
from typing import Literal

from django.contrib.postgres.search import SearchHeadline
from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import F
from django.db.models import Q
from django.db.models import TextField
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import Greatest
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo


SearchResultKind = Literal["collection", "bundle"]


@dataclass(frozen=True, slots=True)
class SearchResult:
    kind: SearchResultKind
    object_id: str
    identifier: str
    title: str
    description: str
    highlight_snippet: str
    url: str
    rank: float


def _build_headline_source(identifier_field: str, title_field: str, description_field: str):
    return Concat(
        Coalesce(F(identifier_field), Value("")),
        Value(" "),
        Coalesce(F(title_field), Value("")),
        Value(" "),
        Coalesce(F(description_field), Value("")),
        output_field=TextField(),
    )


def _highlight_literal_query(text: str, term: str) -> str:
    if not text:
        return ""
    normalized_term = term.strip()
    if not normalized_term:
        return text
    pattern = re.compile(re.escape(normalized_term), flags=re.IGNORECASE)
    return pattern.sub(lambda match: f"<mark>{match.group(0)}</mark>", text)


def _resolve_highlight_snippet(snippet: str | None, description: str, term: str) -> str:
    snippet_text = (snippet or "").strip()
    if snippet_text:
        return snippet_text
    return _highlight_literal_query(description, term)


def _has_mark_highlight(snippet: str) -> bool:
    return "<mark>" in (snippet or "")


def search_archives(term: str, *, limit: int | None = None, use_stored_vectors: bool = True) -> list[SearchResult]:
    """Return ranked search results across collections and bundles.

    Args:
        term: The search term.
        limit: Maximum number of results to return.
        use_stored_vectors: If True, use pre-computed search vectors (fast).
                           If False, compute vectors on the fly (slow, for testing).
    """
    normalized = term.strip()
    if not normalized:
        return []

    # Add prefix matching (:*) to each word for partial word search
    prefix_terms = " & ".join(f"{word}:*" for word in normalized.split())
    query = SearchQuery(prefix_terms, config="simple", search_type="raw")

    collection_results = _search_collections(query, normalized, use_stored_vectors)
    bundle_results = _search_bundles(query, normalized, use_stored_vectors)

    # Supplement with trigram results for typo tolerance (>= 3 chars)
    if len(normalized) >= 3:
        collection_results = [*collection_results, *_trigram_search_collections(normalized)]
        bundle_results = [*bundle_results, *_trigram_search_bundles(normalized)]

    combined: list[SearchResult] = [*collection_results, *bundle_results]
    combined.sort(key=lambda result: result.rank, reverse=True)

    deduped: list[SearchResult] = []
    seen_keys: dict[tuple[str, str], int] = {}

    for result in combined:
        key = (result.kind, result.object_id)
        if key in seen_keys:
            existing_index = seen_keys[key]
            existing = deduped[existing_index]
            # Keep current ordering/rank, but prefer any snippet that actually
            # contains highlights when duplicate hits come from mixed sources.
            if _has_mark_highlight(result.highlight_snippet) and not _has_mark_highlight(existing.highlight_snippet):
                deduped[existing_index] = replace(existing, highlight_snippet=result.highlight_snippet)
            continue
        seen_keys[key] = len(deduped)
        deduped.append(result)

    if limit is None:
        return deduped

    return deduped[:limit]


def _search_collections(query: SearchQuery, term: str, use_stored_vectors: bool = True) -> list[SearchResult]:
    general_info = CollectionGeneralInfo.objects.filter(collection=OuterRef("pk"))
    publication_info = CollectionPublicationInfo.objects.filter(collection=OuterRef("pk"))

    base_qs = Collection.objects.annotate(
        collection_display_title=Subquery(general_info.values("display_title")[:1]),
        collection_description=Subquery(general_info.values("description")[:1]),
        collection_location=Subquery(general_info.values("location__location_name")[:1]),
        collection_country=Subquery(general_info.values("location__country_name")[:1]),
        collection_data_provider=Subquery(publication_info.values("data_provider")[:1]),
    )

    if use_stored_vectors:
        # Use pre-computed search vector (fast, requires rebuild_search_vectors)
        collections = (
            base_qs
            .filter(search_vector__isnull=False)
            .annotate(
                search_rank=SearchRank(F("search_vector"), query),
                highlight_snippet=SearchHeadline(
                    _build_headline_source("identifier", "collection_display_title", "collection_description"),
                    query,
                    config="simple",
                    start_sel="<mark>",
                    stop_sel="</mark>",
                    max_words=30,
                    min_words=8,
                ),
            )
            .filter(search_vector=query)
            .order_by("-search_rank", "identifier")
        )[:50]
    else:
        # Compute search vector on the fly (slow, for testing/fallback)
        collections = (
            base_qs
            .annotate(
                computed_search_vector=(
                    SearchVector("identifier", weight="A", config="simple")
                    + SearchVector("general_info__display_title", weight="A", config="simple")
                    + SearchVector("general_info__description", weight="B", config="simple")
                    + SearchVector("general_info__keywords__value", weight="B", config="simple")
                    + SearchVector("general_info__object_languages__name", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__display_name", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__alternative_names__value", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__taxonomy__language_family__value", weight="C", config="simple")
                    + SearchVector("publication_info__creators__family_name", weight="C", config="simple")
                    + SearchVector("publication_info__contributors__family_name", weight="D", config="simple")
                    + SearchVector("publication_info__data_provider", weight="D", config="simple")
                    + SearchVector("general_info__location__location_name", weight="D", config="simple")
                    + SearchVector("general_info__location__location_facet", weight="D", config="simple")
                    + SearchVector("general_info__location__region_facet", weight="D", config="simple")
                    + SearchVector("general_info__location__country_name", weight="D", config="simple")
                    + SearchVector("general_info__location__country_facet", weight="D", config="simple")
                    + SearchVector("project_infos__project_display_name", weight="D", config="simple")
                    + SearchVector("project_infos__funder_infos__grant_identifier", weight="D", config="simple")
                ),
            )
            .annotate(
                search_rank=SearchRank(F("computed_search_vector"), query),
                highlight_snippet=SearchHeadline(
                    _build_headline_source("identifier", "collection_display_title", "collection_description"),
                    query,
                    config="simple",
                    start_sel="<mark>",
                    stop_sel="</mark>",
                    max_words=30,
                    min_words=8,
                ),
            )
            .filter(Q(computed_search_vector=query))
            .order_by("-search_rank", "identifier")
            .distinct()
        )[:50]

    results: list[SearchResult] = []
    for collection in collections:
        title = collection.collection_display_title or collection.identifier
        description = collection.collection_description or ""
        highlight_snippet = _resolve_highlight_snippet(
            getattr(collection, "highlight_snippet", None),
            description,
            term,
        )
        results.append(
            SearchResult(
                kind="collection",
                object_id=str(collection.pk),
                identifier=collection.identifier,
                title=title,
                description=description,
                highlight_snippet=highlight_snippet,
                url=reverse("explorer:collection_detail", kwargs={"pk": collection.pk}),
                rank=collection.search_rank or 0.0,
            )
        )
    return results


def _search_bundles(query: SearchQuery, term: str, use_stored_vectors: bool = True) -> list[SearchResult]:
    general_info = BundleGeneralInfo.objects.filter(bundle=OuterRef("pk"))
    structural_info = BundleStructuralInfo.objects.filter(bundle=OuterRef("pk"))

    base_qs = Bundle.objects.annotate(
        bundle_display_title=Subquery(general_info.values("display_title")[:1]),
        bundle_description=Subquery(general_info.values("description")[:1]),
        parent_collection_identifier=Subquery(structural_info.values("is_member_of_collection__identifier")[:1]),
        parent_collection_title=Subquery(
            structural_info.values("is_member_of_collection__general_info__display_title")[:1]
        ),
    )

    if use_stored_vectors:
        # Use pre-computed search vector (fast, requires rebuild_search_vectors)
        bundles = (
            base_qs
            .filter(search_vector__isnull=False)
            .annotate(
                search_rank=SearchRank(F("search_vector"), query),
                highlight_snippet=SearchHeadline(
                    _build_headline_source("identifier", "bundle_display_title", "bundle_description"),
                    query,
                    config="simple",
                    start_sel="<mark>",
                    stop_sel="</mark>",
                    max_words=30,
                    min_words=8,
                ),
            )
            .filter(search_vector=query)
            .order_by("-search_rank", "identifier")
        )[:50]
    else:
        # Compute search vector on the fly (slow, for testing/fallback)
        bundles = (
            base_qs
            .annotate(
                computed_search_vector=(
                    SearchVector("identifier", weight="A", config="simple")
                    + SearchVector("general_info__display_title", weight="A", config="simple")
                    + SearchVector("general_info__description", weight="B", config="simple")
                    + SearchVector("structural_info__bundle_topics__name", weight="B", config="simple")
                    + SearchVector("general_info__keywords__value", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__name", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__display_name", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__alternative_names__value", weight="C", config="simple")
                    + SearchVector("general_info__object_languages__bundle_object_language_taxonomy__language_family__value", weight="C", config="simple")
                    + SearchVector("general_info__location__location_facet", weight="D", config="simple")
                    + SearchVector("general_info__location__region_facet", weight="D", config="simple")
                    + SearchVector("general_info__location__country_facet", weight="D", config="simple")
                    + SearchVector("projects__project_display_name", weight="D", config="simple")
                    + SearchVector("projects__funder_infos__grant_identifier", weight="D", config="simple")
                    + SearchVector("structural_info__is_member_of_collection__identifier", weight="D", config="simple")
                    + SearchVector("structural_info__is_member_of_collection__general_info__display_title", weight="D", config="simple")
                ),
            )
            .annotate(
                search_rank=SearchRank(F("computed_search_vector"), query),
                highlight_snippet=SearchHeadline(
                    _build_headline_source("identifier", "bundle_display_title", "bundle_description"),
                    query,
                    config="simple",
                    start_sel="<mark>",
                    stop_sel="</mark>",
                    max_words=30,
                    min_words=8,
                ),
            )
            .filter(Q(computed_search_vector=query))
            .order_by("-search_rank", "identifier")
            .distinct()
        )[:50]

    results: list[SearchResult] = []
    for bundle in bundles:
        title = bundle.bundle_display_title or bundle.identifier
        description = bundle.bundle_description or ""
        highlight_snippet = _resolve_highlight_snippet(
            getattr(bundle, "highlight_snippet", None),
            description,
            term,
        )
        results.append(
            SearchResult(
                kind="bundle",
                object_id=str(bundle.pk),
                identifier=bundle.identifier,
                title=title,
                description=description,
                highlight_snippet=highlight_snippet,
                url=reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}),
                rank=bundle.search_rank or 0.0,
            )
        )
    return results


def _trigram_search_collections(search_term: str) -> list[SearchResult]:
    general_info = CollectionGeneralInfo.objects.filter(collection=OuterRef("pk"))

    collections = (
        Collection.objects.annotate(
            collection_display_title=Subquery(general_info.values("display_title")[:1]),
            collection_description=Subquery(general_info.values("description")[:1]),
            similarity=Greatest(
                TrigramWordSimilarity(search_term, "general_info__display_title"),
                TrigramWordSimilarity(search_term, "identifier"),
            ),
        )
        .filter(similarity__gt=0.3)
        .distinct()
        .order_by("-similarity", "identifier")
    )[:50]

    results: list[SearchResult] = []
    for collection in collections:
        title = collection.collection_display_title or collection.identifier
        description = collection.collection_description or ""
        results.append(
            SearchResult(
                kind="collection",
                object_id=str(collection.pk),
                identifier=collection.identifier,
                title=title,
                description=description,
                highlight_snippet=_resolve_highlight_snippet(None, description, search_term),
                url=reverse("explorer:collection_detail", kwargs={"pk": collection.pk}),
                rank=collection.similarity or 0.0,
            )
        )
    return results


def _trigram_search_bundles(search_term: str) -> list[SearchResult]:
    general_info = BundleGeneralInfo.objects.filter(bundle=OuterRef("pk"))
    structural_info = BundleStructuralInfo.objects.filter(bundle=OuterRef("pk"))

    bundles = (
        Bundle.objects.annotate(
            bundle_display_title=Subquery(general_info.values("display_title")[:1]),
            bundle_description=Subquery(general_info.values("description")[:1]),
            parent_collection_identifier=Subquery(structural_info.values("is_member_of_collection__identifier")[:1]),
            similarity=Greatest(
                TrigramWordSimilarity(search_term, "general_info__display_title"),
                TrigramWordSimilarity(search_term, "identifier"),
            ),
        )
        .filter(similarity__gt=0.3)
        .distinct()
        .order_by("-similarity", "identifier")
    )[:50]

    results: list[SearchResult] = []
    for bundle in bundles:
        title = bundle.bundle_display_title or bundle.identifier
        description = bundle.bundle_description or ""
        results.append(
            SearchResult(
                kind="bundle",
                object_id=str(bundle.pk),
                identifier=bundle.identifier,
                title=title,
                description=description,
                highlight_snippet=_resolve_highlight_snippet(None, description, search_term),
                url=reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}),
                rank=bundle.similarity or 0.0,
            )
        )
    return results
