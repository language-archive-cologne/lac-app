from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import F
from django.db.models import Q
from django.db.models.functions import Coalesce
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
    url: str
    rank: float


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

    collection_results = _search_collections(query, use_stored_vectors)
    bundle_results = _search_bundles(query, use_stored_vectors)

    # Trigram fallback when FTS returns nothing
    if not collection_results and not bundle_results and len(normalized) >= 3:
        collection_results = _trigram_search_collections(normalized)
        bundle_results = _trigram_search_bundles(normalized)

    combined: list[SearchResult] = [*collection_results, *bundle_results]
    combined.sort(key=lambda result: result.rank, reverse=True)

    deduped: list[SearchResult] = []
    seen_keys: set[tuple[str, str]] = set()

    for result in combined:
        key = (result.kind, result.object_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(result)

    if limit is None:
        return deduped

    return deduped[:limit]


def _search_collections(query: SearchQuery, use_stored_vectors: bool = True) -> list[SearchResult]:
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
            .annotate(search_rank=SearchRank(F("search_vector"), query))
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
            .annotate(search_rank=SearchRank(F("computed_search_vector"), query))
            .filter(Q(computed_search_vector=query))
            .order_by("-search_rank", "identifier")
            .distinct()
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
                url=reverse("explorer:collection_detail", kwargs={"pk": collection.pk}),
                rank=collection.search_rank or 0.0,
            )
        )
    return results


def _search_bundles(query: SearchQuery, use_stored_vectors: bool = True) -> list[SearchResult]:
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
            .annotate(search_rank=SearchRank(F("search_vector"), query))
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
            .annotate(search_rank=SearchRank(F("computed_search_vector"), query))
            .filter(Q(computed_search_vector=query))
            .order_by("-search_rank", "identifier")
            .distinct()
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
                url=reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}),
                rank=bundle.similarity or 0.0,
            )
        )
    return results
