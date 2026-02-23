"""Tests for advanced per-field search filtering."""

from django.http import QueryDict

from lacos.explorer.advanced_search import (
    BUNDLE_FIELD_DEFINITIONS,
    COLLECTION_FIELD_DEFINITIONS,
    parse_advanced_params,
)


class TestCollectionFieldDefinitions:
    def test_definitions_exist(self):
        assert len(COLLECTION_FIELD_DEFINITIONS) > 0

    def test_expected_fields_present(self):
        names = [d.param_name for d in COLLECTION_FIELD_DEFINITIONS]
        assert "field_title" in names
        assert "field_description" in names
        assert "field_keyword" in names
        assert "field_language" in names
        assert "field_location" in names
        assert "field_creator" in names
        assert "field_contributor" in names
        assert "field_grant_id" in names
        assert "field_data_provider" in names

    def test_all_have_required_attributes(self):
        for defn in COLLECTION_FIELD_DEFINITIONS:
            assert defn.param_name
            assert defn.label
            assert defn.orm_lookups


class TestBundleFieldDefinitions:
    def test_definitions_exist(self):
        assert len(BUNDLE_FIELD_DEFINITIONS) > 0

    def test_bundle_specific_fields_present(self):
        names = [d.param_name for d in BUNDLE_FIELD_DEFINITIONS]
        assert "field_collection" in names
        assert "field_topic" in names

    def test_no_data_provider(self):
        names = [d.param_name for d in BUNDLE_FIELD_DEFINITIONS]
        assert "field_data_provider" not in names


class TestParseAdvancedParams:
    def test_empty_params(self):
        result = parse_advanced_params(QueryDict(""), COLLECTION_FIELD_DEFINITIONS)
        assert result == {}

    def test_extracts_field_params(self):
        result = parse_advanced_params(
            QueryDict("field_title=Senufo&field_description=music"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert result["field_title"] == "Senufo"
        assert result["field_description"] == "music"

    def test_ignores_non_field_params(self):
        result = parse_advanced_params(
            QueryDict("q=test&sort=name&field_title=X"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert "q" not in result
        assert "sort" not in result
        assert result["field_title"] == "X"

    def test_strips_whitespace(self):
        result = parse_advanced_params(
            QueryDict("field_title=+Senufo+"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert result["field_title"] == "Senufo"

    def test_skips_empty_values(self):
        result = parse_advanced_params(
            QueryDict("field_title=&field_description=music"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert "field_title" not in result
        assert result["field_description"] == "music"

    def test_ignores_unknown_field_params(self):
        result = parse_advanced_params(
            QueryDict("field_bogus=test&field_title=X"),
            COLLECTION_FIELD_DEFINITIONS,
        )
        assert "field_bogus" not in result
        assert result["field_title"] == "X"
