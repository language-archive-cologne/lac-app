"""Tests for advanced per-field search filtering."""

from django.http import QueryDict

from lacos.explorer.advanced_search import (
    BUNDLE_FIELD_DEFINITIONS,
    COLLECTION_FIELD_DEFINITIONS,
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
        assert "data_provider" in keys

    def test_all_have_required_attributes(self):
        for defn in COLLECTION_FIELD_DEFINITIONS:
            assert defn.key
            assert defn.label
            assert defn.orm_lookups


class TestBundleFieldDefinitions:
    def test_definitions_exist(self):
        assert len(BUNDLE_FIELD_DEFINITIONS) > 0

    def test_bundle_specific_fields_present(self):
        keys = [d.key for d in BUNDLE_FIELD_DEFINITIONS]
        assert "collection" in keys
        assert "topic" in keys

    def test_no_data_provider(self):
        keys = [d.key for d in BUNDLE_FIELD_DEFINITIONS]
        assert "data_provider" not in keys


class TestParseSearchRows:
    def test_empty_params(self):
        result = parse_search_rows(QueryDict(""), COLLECTION_FIELD_DEFINITIONS)
        assert result == []

    def test_single_row(self):
        result = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=Senufo"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "title"
        assert result[0].value == "Senufo"
        assert result[0].index == 0

    def test_multiple_rows(self):
        result = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=Senufo&row_1_field=language&row_1_value=Bambara"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 2
        assert result[0].field_key == "title"
        assert result[0].value == "Senufo"
        assert result[1].field_key == "language"
        assert result[1].value == "Bambara"

    def test_skips_empty_values(self):
        result = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=&row_1_field=language&row_1_value=Bambara"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "language"

    def test_skips_invalid_field_keys(self):
        result = parse_search_rows(
            QueryDict("row_0_field=bogus&row_0_value=test&row_1_field=title&row_1_value=X"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "title"

    def test_strips_whitespace(self):
        result = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=+Senufo+"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].value == "Senufo"

    def test_ignores_non_row_params(self):
        result = parse_search_rows(
            QueryDict("q=test&sort=name&row_0_field=title&row_0_value=X"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 1
        assert result[0].field_key == "title"

    def test_handles_gaps_in_indices(self):
        result = parse_search_rows(
            QueryDict("row_0_field=title&row_0_value=A&row_5_field=language&row_5_value=B"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert len(result) == 2
        assert result[0].index == 0
        assert result[1].index == 5

    def test_skips_row_missing_field(self):
        result = parse_search_rows(
            QueryDict("row_0_value=Senufo"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert result == []

    def test_skips_row_missing_value(self):
        result = parse_search_rows(
            QueryDict("row_0_field=title"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert result == []
