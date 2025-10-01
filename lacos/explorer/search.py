from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.contrib.postgres.aggregates import StringAgg
from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.db.models import CharField
from django.db.models import OuterRef
from django.db.models import TextField
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import F
from django.db.models import Q
from django.db.models.functions import Cast
from django.db.models.functions import Coalesce
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


def search_archives(term: str, *, limit: int | None = None) -> list[SearchResult]:
    """Return ranked search results across collections and bundles."""
    normalized = term.strip()
    if not normalized:
        return []

    query = SearchQuery(normalized, config="simple")

    collection_results = _search_collections(query)
    bundle_results = _search_bundles(query)

    combined: list[SearchResult] = [*collection_results, *bundle_results]
    combined.sort(key=lambda result: result.rank, reverse=True)

    if limit is None:
        return combined

    return combined[:limit]


def _search_collections(query: SearchQuery) -> list[SearchResult]:
    general_info = CollectionGeneralInfo.objects.filter(collection=OuterRef("pk"))
    publication_info = CollectionPublicationInfo.objects.filter(collection=OuterRef("pk"))

    collections = (
        Collection.objects
        .annotate(
            collection_display_title=Subquery(general_info.values("display_title")[:1]),
            collection_description=Subquery(general_info.values("description")[:1]),
            collection_keywords=StringAgg(
                "general_info__keywords__value",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            collection_languages=StringAgg(
                "general_info__object_languages__name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            collection_location=Subquery(general_info.values("location__location_name")[:1]),
            collection_country=Subquery(general_info.values("location__country_name")[:1]),
            collection_creators=StringAgg(
                "publication_info__creators__family_name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            collection_contributors=StringAgg(
                "publication_info__contributors__family_name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            collection_data_provider=Subquery(publication_info.values("data_provider")[:1]),
        )
        .annotate(
            collection_search_vector=(
                SearchVector("identifier", weight="A", config="simple")
                + SearchVector(
                    Coalesce(
                        Cast("collection_display_title", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="A",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_description", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="B",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_keywords", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="B",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_languages", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_creators", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_contributors", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="D",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_data_provider", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="D",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_location", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="D",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("collection_country", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="D",
                    config="simple",
                )
            )
        )
        .annotate(search_rank=SearchRank(F("collection_search_vector"), query))
        .filter(Q(collection_search_vector=query))
        .order_by("-search_rank", "identifier")
    )

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


def _search_bundles(query: SearchQuery) -> list[SearchResult]:
    general_info = BundleGeneralInfo.objects.filter(bundle=OuterRef("pk"))
    structural_info = BundleStructuralInfo.objects.filter(bundle=OuterRef("pk"))

    bundles = (
        Bundle.objects
        .annotate(
            bundle_display_title=Subquery(general_info.values("display_title")[:1]),
            bundle_description=Subquery(general_info.values("description")[:1]),
            bundle_keywords_text=StringAgg(
                "general_info__keywords__value",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            bundle_languages_text=StringAgg(
                "general_info__object_languages__name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            bundle_topics_text=StringAgg(
                "structural_info__bundle_topics__name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            bundle_media_files_text=StringAgg(
                "resources__bundle_media_resources__file_name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            bundle_written_files_text=StringAgg(
                "resources__bundle_written_resources__file_name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            bundle_other_files_text=StringAgg(
                "resources__bundle_other_resources__file_name",
                delimiter=" ",
                distinct=True,
                default=Value("", output_field=TextField()),
            ),
            parent_collection_identifier=Subquery(structural_info.values("is_member_of_collection__identifier")[:1]),
            parent_collection_title=Subquery(
                structural_info.values("is_member_of_collection__general_info__display_title")[:1]
            ),
        )
        .annotate(
            bundle_search_vector=(
                SearchVector("identifier", weight="A", config="simple")
                + SearchVector(
                    Coalesce(
                        Cast("bundle_display_title", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="A",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_description", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="B",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_topics_text", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="B",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_keywords_text", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_languages_text", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_media_files_text", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_written_files_text", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("bundle_other_files_text", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="C",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("parent_collection_identifier", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="D",
                    config="simple",
                )
                + SearchVector(
                    Coalesce(
                        Cast("parent_collection_title", TextField()),
                        Value("", output_field=TextField()),
                        output_field=TextField(),
                    ),
                    weight="D",
                    config="simple",
                )
            )
        )
        .annotate(search_rank=SearchRank(F("bundle_search_vector"), query))
        .filter(Q(bundle_search_vector=query))
        .order_by("-search_rank", "identifier")
    )

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
