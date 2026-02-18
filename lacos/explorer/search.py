from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import re
from typing import Literal

from django.contrib.postgres.search import SearchHeadline
from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import F
from django.db.models import Q
from django.db.models import TextField
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
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
    matched_fields: tuple[str, ...]
    url: str
    rank: float
    keywords: tuple[str, ...] = ()
    parent_collection_identifier: str = ""
    parent_collection_title: str = ""
    parent_collection_url: str = ""


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


def _tokenize_search_term(term: str) -> list[str]:
    return [token.lower() for token in term.split() if token.strip()]


def _matches_prefix_token(text: str, tokens: list[str]) -> bool:
    if not text or not tokens:
        return False
    lowered = text.lower()
    words = re.findall(r"\w+", lowered)
    return any(token in lowered or any(word.startswith(token) for word in words) for token in tokens)


def _infer_matched_fields(
    term: str,
    field_values: list[tuple[str, str]],
) -> tuple[str, ...]:
    tokens = _tokenize_search_term(term)
    matched = [label for label, value in field_values if _matches_prefix_token(value, tokens)]
    if matched:
        return tuple(matched)

    return ("metadata",)


def _has_mark_highlight(snippet: str) -> bool:
    return "<mark>" in (snippet or "")


def _collection_keywords_by_object_id(
    collections: list[Collection],
) -> dict[str, tuple[str, ...]]:
    object_ids = [collection.pk for collection in collections]
    if not object_ids:
        return {}

    keyword_map: dict[str, tuple[str, ...]] = {}
    for general_info in CollectionGeneralInfo.objects.filter(
        collection_id__in=object_ids
    ).prefetch_related("keywords"):
        values = tuple(
            keyword.value for keyword in general_info.keywords.all() if keyword.value
        )
        if values:
            keyword_map[str(general_info.collection_id)] = values
    return keyword_map


def _bundle_keywords_by_object_id(
    bundles: list[Bundle],
) -> dict[str, tuple[str, ...]]:
    object_ids = [bundle.pk for bundle in bundles]
    if not object_ids:
        return {}

    keyword_map: dict[str, tuple[str, ...]] = {}
    for general_info in BundleGeneralInfo.objects.filter(
        bundle_id__in=object_ids
    ).prefetch_related("keywords"):
        values = tuple(
            keyword.value for keyword in general_info.keywords.all() if keyword.value
        )
        if values:
            keyword_map[str(general_info.bundle_id)] = values
    return keyword_map


def _full_name(given_name: str | None, family_name: str | None) -> str:
    given = (given_name or "").strip()
    family = (family_name or "").strip()
    if given and family:
        return f"{given} {family}"
    return family or given


def _collection_people_text(collection: Collection) -> tuple[str, str]:
    publication = getattr(collection, "get_publication_info", None)
    if not publication:
        return "", ""

    creator_terms: list[str] = []
    for creator in publication.creators.all():
        creator_terms.append((creator.family_name or "").strip())
        creator_terms.append((creator.given_name or "").strip())
        creator_terms.append(_full_name(creator.given_name, creator.family_name))

    contributor_terms: list[str] = []
    for contributor in publication.contributors.all():
        contributor_terms.append((contributor.family_name or "").strip())
        contributor_terms.append((contributor.given_name or "").strip())
        contributor_terms.append(
            (getattr(contributor, "contributor_display_name", "") or "").strip()
        )
        contributor_terms.append((contributor.role or "").strip())
        contributor_terms.append(_full_name(contributor.given_name, contributor.family_name))

    creators = " ".join(term for term in creator_terms if term)
    contributors = " ".join(term for term in contributor_terms if term)
    return creators, contributors


def _bundle_people_text(bundle: Bundle) -> tuple[str, str]:
    publication = getattr(bundle, "get_publication_info", None)
    if not publication:
        return "", ""

    creator_terms: list[str] = []
    for creator in publication.creators.all():
        creator_terms.append((creator.family_name or "").strip())
        creator_terms.append((creator.given_name or "").strip())
        creator_terms.append(_full_name(creator.given_name, creator.family_name))

    contributor_terms: list[str] = []
    for contributor in publication.contributors.all():
        contributor_terms.append((contributor.family_name or "").strip())
        contributor_terms.append((contributor.given_name or "").strip())
        contributor_terms.append((contributor.role or "").strip())
        contributor_terms.append(_full_name(contributor.given_name, contributor.family_name))
        contributor_name = getattr(contributor, "contributor_name", None)
        if contributor_name:
            contributor_terms.append((contributor_name.contributor_family_name or "").strip())
            contributor_terms.append((contributor_name.contributor_given_name or "").strip())
            contributor_terms.append(
                _full_name(
                    contributor_name.contributor_given_name,
                    contributor_name.contributor_family_name,
                )
            )

    creators = " ".join(term for term in creator_terms if term)
    contributors = " ".join(term for term in contributor_terms if term)
    return creators, contributors


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

    combined: list[SearchResult] = [*collection_results, *bundle_results]
    combined.sort(key=lambda result: result.rank, reverse=True)

    deduped: list[SearchResult] = []
    seen_keys: dict[tuple[str, str], int] = {}

    for result in combined:
        key = (result.kind, result.object_id)
        if key in seen_keys:
            existing_index = seen_keys[key]
            existing = deduped[existing_index]
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
            .prefetch_related(
                "publication_info__creators",
                "publication_info__contributors",
            )
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
                    + SearchVector("publication_info__creators__given_name", weight="C", config="simple")
                    + SearchVector("publication_info__contributors__family_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__given_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__contributor_display_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__role", weight="D", config="simple")
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
            .prefetch_related(
                "publication_info__creators",
                "publication_info__contributors",
            )
        )[:50]
    collection_rows = list(collections)
    keywords_by_collection = _collection_keywords_by_object_id(collection_rows)

    results: list[SearchResult] = []
    for collection in collection_rows:
        title = collection.collection_display_title or collection.identifier
        description = collection.collection_description or ""
        keywords = keywords_by_collection.get(str(collection.pk), ())
        creator_terms, contributor_terms = _collection_people_text(collection)
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
                matched_fields=_infer_matched_fields(
                    term,
                    [
                        ("identifier", collection.identifier),
                        ("title", title),
                        ("description", description),
                        ("keywords", " ".join(keywords)),
                        ("location", collection.collection_location or ""),
                        ("country", collection.collection_country or ""),
                        ("data provider", collection.collection_data_provider or ""),
                        ("creator", creator_terms),
                        ("contributor", contributor_terms),
                    ],
                ),
                url=reverse("explorer:collection_detail", kwargs={"pk": collection.pk}),
                rank=collection.search_rank or 0.0,
                keywords=keywords,
            )
        )
    return results


def _search_bundles(query: SearchQuery, term: str, use_stored_vectors: bool = True) -> list[SearchResult]:
    general_info = BundleGeneralInfo.objects.filter(bundle=OuterRef("pk"))
    structural_info = BundleStructuralInfo.objects.filter(bundle=OuterRef("pk"))
    publication_info = BundlePublicationInfo.objects.filter(bundle=OuterRef("pk"))

    base_qs = Bundle.objects.annotate(
        bundle_display_title=Subquery(general_info.values("display_title")[:1]),
        bundle_description=Subquery(general_info.values("description")[:1]),
        parent_collection_identifier=Subquery(structural_info.values("is_member_of_collection__identifier")[:1]),
        parent_collection_title=Subquery(
            structural_info.values("is_member_of_collection__general_info__display_title")[:1]
        ),
        bundle_data_provider=Subquery(publication_info.values("data_provider")[:1]),
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
            .prefetch_related(
                "publication_info__creators",
                "publication_info__contributors__contributor_name",
            )
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
                    + SearchVector("publication_info__creators__family_name", weight="C", config="simple")
                    + SearchVector("publication_info__creators__given_name", weight="C", config="simple")
                    + SearchVector("publication_info__contributors__family_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__given_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__contributor_name__contributor_family_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__contributor_name__contributor_given_name", weight="D", config="simple")
                    + SearchVector("publication_info__contributors__role", weight="D", config="simple")
                    + SearchVector("publication_info__data_provider", weight="D", config="simple")
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
            .prefetch_related(
                "publication_info__creators",
                "publication_info__contributors__contributor_name",
            )
        )[:50]
    bundle_rows = list(bundles)
    keywords_by_bundle = _bundle_keywords_by_object_id(bundle_rows)

    results: list[SearchResult] = []
    for bundle in bundle_rows:
        title = bundle.bundle_display_title or bundle.identifier
        description = bundle.bundle_description or ""
        keywords = keywords_by_bundle.get(str(bundle.pk), ())
        creator_terms, contributor_terms = _bundle_people_text(bundle)
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
                matched_fields=_infer_matched_fields(
                    term,
                    [
                        ("identifier", bundle.identifier),
                        ("title", title),
                        ("description", description),
                        ("keywords", " ".join(keywords)),
                        ("parent collection identifier", bundle.parent_collection_identifier or ""),
                        ("parent collection title", bundle.parent_collection_title or ""),
                        ("data provider", bundle.bundle_data_provider or ""),
                        ("creator", creator_terms),
                        ("contributor", contributor_terms),
                    ],
                ),
                url=reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}),
                rank=bundle.search_rank or 0.0,
                keywords=keywords,
                parent_collection_identifier=bundle.parent_collection_identifier or "",
                parent_collection_title=bundle.parent_collection_title or "",
                parent_collection_url=(
                    reverse(
                        "explorer:collection_detail_by_handle",
                        kwargs={"handle": bundle.parent_collection_identifier},
                    )
                    if bundle.parent_collection_identifier
                    else ""
                ),
            )
        )
    return results
