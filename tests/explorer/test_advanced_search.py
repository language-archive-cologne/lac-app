"""Tests for advanced per-field search filtering."""

import pytest
from django.http import QueryDict

from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.explorer.advanced_search import (
    BUNDLE_FIELD_DEFINITIONS,
    COLLECTION_FIELD_DEFINITIONS,
    SearchRow,
    apply_search_rows,
    parse_search_rows,
)


class TestCollectionFieldDefinitions:
    def test_definitions_exist(self):
        assert len(COLLECTION_FIELD_DEFINITIONS) > 0

    def test_expected_fields_present(self):
        keys = [d.key for d in COLLECTION_FIELD_DEFINITIONS]
        assert "title" in keys
        assert "description" in keys
        assert "keyword" in keys
        assert "language" in keys
        assert "location" in keys
        assert "creator" in keys
        assert "contributor" in keys
        assert "grant_id" in keys

    def test_all_have_required_attributes(self):
        for defn in COLLECTION_FIELD_DEFINITIONS:
            assert defn.key
            assert defn.label
            assert defn.orm_fields


class TestBundleFieldDefinitions:
    def test_definitions_exist(self):
        assert len(BUNDLE_FIELD_DEFINITIONS) > 0

    def test_bundle_specific_fields_present(self):
        keys = [d.key for d in BUNDLE_FIELD_DEFINITIONS]
        assert "collection" in keys

    def test_no_data_provider(self):
        keys = [d.key for d in BUNDLE_FIELD_DEFINITIONS]
        assert "data_provider" not in keys


class TestParseSearchRows:
    def test_empty_params(self):
        result, _ = parse_search_rows(QueryDict(""), COLLECTION_FIELD_DEFINITIONS)
        assert result == []

    def test_single_row(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=Senufo"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "title"
        assert result[0].value == "Senufo"
        assert result[0].index == 0

    def test_multiple_rows(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=Senufo&row_1_field=language&row_1_value=Bambara"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 2
        assert result[0].field_key == "title"
        assert result[0].value == "Senufo"
        assert result[1].field_key == "language"
        assert result[1].value == "Bambara"

    def test_skips_empty_values(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=&row_1_field=language&row_1_value=Bambara"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "language"

    def test_skips_invalid_field_keys(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=bogus&row_0_value=test&row_1_field=title&row_1_value=X"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "title"

    def test_strips_whitespace(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=+Senufo+"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].value == "Senufo"

    def test_ignores_non_row_params(self):
        result, _ = parse_search_rows(
            QueryDict("q=test&sort=name&row_0_field=title&row_0_value=X"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "title"

    def test_handles_gaps_in_indices(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=A&row_5_field=language&row_5_value=B"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 2
        assert result[0].index == 0
        assert result[1].index == 5

    def test_skips_row_missing_field(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_value=Senufo"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert result == []

    def test_skips_row_missing_value(self):
        result, _ = parse_search_rows(
            QueryDict("row_0_field=title"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert result == []


def _create_collection(
    identifier: str,
    title: str,
    *,
    languages: list[tuple[str, str]] | None = None,
    country: str | None = None,
    region: str | None = None,
    location_name: str | None = None,
    description: str | None = None,
    keywords: list[str] | None = None,
) -> Collection:
    """Helper to create a collection with related metadata."""
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        country_facet=country or "",
        country_name=country or "",
        country_code=(country[:2].upper() if country else ""),
        region_facet=region or "",
        location_name=location_name or "",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"CID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=description or f"Description for {title}",
        location=location,
        version="1.0",
    )
    if languages:
        for name, iso_code in languages:
            lang = CollectionObjectLanguage.objects.create(
                display_name=name, name=name,
                iso_639_3_code=iso_code, glottolog_code=f"{iso_code}1234",
            )
            general_info.object_languages.add(lang)
    if keywords:
        for kw in keywords:
            keyword_obj = CollectionKeyword.objects.create(value=kw)
            general_info.keywords.add(keyword_obj)
    return collection


@pytest.mark.django_db
class TestApplySearchRowsFTS:
    """Integration tests for FTS-based field search filtering."""

    def test_prefix_match(self):
        _create_collection("col-1", "Senufo Language Archive")
        _create_collection("col-2", "Bambara Collection")

        rows = [SearchRow(field_key="title", value="sen", index=0)]
        qs = apply_search_rows(Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 1
        assert qs.first().identifier == "col-1"

    def test_mid_word_no_match(self):
        _create_collection("col-1", "Senufo Language Archive")

        rows = [SearchRow(field_key="title", value="nufo", index=0)]
        qs = apply_search_rows(Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 0

    def test_multi_word_and(self):
        _create_collection("col-1", "Senufo Language Archive")
        _create_collection("col-2", "Senufo Music Collection")

        rows = [SearchRow(field_key="title", value="senufo arch", index=0)]
        qs = apply_search_rows(Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 1
        assert qs.first().identifier == "col-1"

    def test_special_characters_safe(self):
        _create_collection("col-1", "Rock and Roll Archive")

        rows = [SearchRow(field_key="title", value="Rock & Roll", index=0)]
        qs = apply_search_rows(Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 1

    def test_and_logic_across_rows(self):
        _create_collection("col-1", "Senufo Language Archive",
                           languages=[("Bambara", "bam")])
        _create_collection("col-2", "Senufo Music Collection",
                           languages=[("French", "fra")])

        rows = [
            SearchRow(field_key="title", value="Senufo", index=0),
            SearchRow(field_key="language", value="Bambara", index=1),
        ]
        qs = apply_search_rows(
            Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS, logic="and",
        )
        assert qs.count() == 1
        assert qs.first().identifier == "col-1"

    def test_or_logic_across_rows(self):
        _create_collection("col-1", "Senufo Language Archive")
        _create_collection("col-2", "Bambara Music Collection")
        _create_collection("col-3", "Unrelated Data")

        rows = [
            SearchRow(field_key="title", value="Senufo", index=0),
            SearchRow(field_key="title", value="Bambara", index=1),
        ]
        qs = apply_search_rows(
            Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS, logic="or",
        )
        assert qs.count() == 2
        identifiers = set(qs.values_list("identifier", flat=True))
        assert identifiers == {"col-1", "col-2"}

    def test_multi_field_location(self):
        _create_collection("col-1", "Test Collection",
                           country="Papua New Guinea", region="Oceania")
        _create_collection("col-2", "Other Collection", country="Germany")

        rows = [SearchRow(field_key="location", value="Papua", index=0)]
        qs = apply_search_rows(Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 1
        assert qs.first().identifier == "col-1"

    def test_empty_rows_returns_unchanged(self):
        _create_collection("col-1", "Test Collection")

        qs = apply_search_rows(Collection.objects.all(), [], COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 1

    def test_only_special_chars_returns_unchanged(self):
        _create_collection("col-1", "Test Collection")

        rows = [SearchRow(field_key="title", value="&!@#", index=0)]
        qs = apply_search_rows(Collection.objects.all(), rows, COLLECTION_FIELD_DEFINITIONS)
        assert qs.count() == 1
