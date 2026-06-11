from __future__ import annotations

import pytest
from django.template import Context, Template
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleKeyword
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_general_info import BundleObjectLanguage
from lacos.blam.models.bundle.bundle_general_info import BundleObjectLanguageAlternativeName
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionKeyword
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_general_info import CollectionObjectLanguage
from lacos.blam.models.collection.collection_general_info import CollectionObjectLanguageAlternativeName
from lacos.blam.models.collection.collection_publication_info import CollectionCreator
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.explorer.search import search_archives
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.storage.services.exposure_policy_service import ExposurePolicyService


@pytest.mark.django_db
def test_collection_search_matches_title_and_keywords():
    collection = Collection.objects.create(identifier="COL-001")
    location = CollectionLocation.objects.create(
        geo_location="50.9375,6.9603",
        location_name="Cologne",
        region_name="North Rhine-Westphalia",
        country_name="Germany",
        country_code="DE",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Extensive documentation of the Senufo languages.",
        location=location,
        version="1.0",
    )
    keyword = CollectionKeyword.objects.create(value="senufo")
    language = CollectionObjectLanguage.objects.create(
        display_name="Senufo",
        name="Senufo",
        iso_639_3_code="sef",
        glottolog_code="senu1234",
    )
    general_info.keywords.add(keyword)
    general_info.object_languages.add(language)

    publication_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    creator = CollectionCreator.objects.create(family_name="Diallo")
    publication_info.creators.add(creator)

    results = search_archives("senufo", use_stored_vectors=False)

    assert any(result.kind == "collection" and result.object_id == str(collection.pk) for result in results)


@pytest.mark.django_db
def test_fts_results_include_highlight_snippet():
    collection = Collection.objects.create(identifier="COL-HL-001")
    location = CollectionLocation.objects.create(
        location_name="Korhogo",
        country_name="Ivory Coast",
        country_code="CI",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-HL-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Documentation resources for Senufo speakers.",
        location=location,
        version="1.0",
    )

    # Two-letter prefix query should still exercise the FTS snippet path.
    results = search_archives("se", use_stored_vectors=False)
    match = next(
        result
        for result in results
        if result.kind == "collection" and result.object_id == str(collection.pk)
    )

    assert match.highlight_snippet
    assert "<mark>" in match.highlight_snippet


@pytest.mark.django_db
def test_fts_results_include_matched_fields():
    collection = Collection.objects.create(identifier="COL-MATCH-001")
    location = CollectionLocation.objects.create(
        location_name="Korhogo",
        country_name="Ivory Coast",
        country_code="CI",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-MATCH-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Documentation resources for Senufo speakers.",
        location=location,
        version="1.0",
    )

    results = search_archives("senufo", use_stored_vectors=False)
    match = next(
        result
        for result in results
        if result.kind == "collection" and result.object_id == str(collection.pk)
    )

    assert "title" in match.matched_fields


@pytest.mark.django_db
def test_fts_query_highlights_description_matches():
    collection = Collection.objects.create(identifier="COL-LIT-HL-001")
    location = CollectionLocation.objects.create(
        location_name="Bogota",
        country_name="Colombia",
        country_code="CO",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-LIT-HL-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Language Variety Archive",
        description="Documentation of language variety in Latin America.",
        location=location,
        version="1.0",
    )

    results = search_archives("var", use_stored_vectors=False)
    match = next(
        result
        for result in results
        if result.kind == "collection" and result.object_id == str(collection.pk)
    )
    assert "<mark>" in match.highlight_snippet
    assert "description" in match.matched_fields


@pytest.mark.django_db
def test_bundle_search_matches_topics_and_parent_collection():
    collection = Collection.objects.create(identifier="COL-RES")
    collection_location = CollectionLocation.objects.create(
        location_name="Accra",
        country_name="Ghana",
        country_code="GH",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-100",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Ghana Oral Histories",
        description="Source material for Ghanaian narratives.",
        location=collection_location,
        version="1.0",
    )

    bundle = Bundle.objects.create(identifier="BND-001")
    bundle_location = BundleLocation.objects.create(location_name="Accra")
    bundle_general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value="BID-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Evening Stories",
        description="Audio recordings of evening storytelling sessions.",
        location=bundle_location,
        version="1.0",
    )
    bundle_keyword = BundleKeyword.objects.create(value="storytelling")
    bundle_language = BundleObjectLanguage.objects.create(
        display_name="Akan",
        name="Akan",
        iso_639_3_code="aka",
        glottolog_code="akan1254",
    )
    bundle_general_info.keywords.add(bundle_keyword)
    bundle_general_info.object_languages.add(bundle_language)

    structural_info = BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    media_resource = MediaResource.objects.create(
        file_name="story_evening_01.wav",
        file_pid="pid:story1",
        mime_type="audio/wav",
        file_length="00:15:00",
    )
    bundle_resources.bundle_media_resources.add(media_resource)

    by_topic = search_archives("history", use_stored_vectors=False)
    assert any(result.kind == "bundle" and result.object_id == str(bundle.pk) for result in by_topic)

    by_parent_identifier = search_archives("COL-RES", use_stored_vectors=False)
    assert any(result.kind == "bundle" and result.object_id == str(bundle.pk) for result in by_parent_identifier)


@pytest.mark.django_db
def test_search_ignores_blank_terms():
    assert search_archives("   ") == []


@pytest.mark.django_db
def test_search_excludes_collection_when_policy_disallows_it(monkeypatch):
    collection = Collection.objects.create(identifier="COL-SEARCH-FILTER-001")
    location = CollectionLocation.objects.create(
        location_name="Bamako",
        country_name="Mali",
        country_code="ML",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-SEARCH-FILTER-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Filtered Search Collection",
        description="Collection hidden by exposure policy.",
        location=location,
        version="1.0",
    )

    def _can_list_in_search(self, user, obj):
        if isinstance(obj, Collection) and obj.pk == collection.pk:
            return False
        return True

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_list_in_search",
        _can_list_in_search,
    )

    results = search_archives("Filtered", use_stored_vectors=False)

    assert not any(
        result.kind == "collection" and result.object_id == str(collection.pk)
        for result in results
    )


@pytest.mark.django_db
def test_collection_search_matches_object_language_alternative_name():
    """Test that collections can be found by searching for language alternative names."""
    collection = Collection.objects.create(identifier="COL-ALTNAME-001")
    location = CollectionLocation.objects.create(
        geo_location="22.5726,88.3639",
        location_name="Kolkata",
        region_name="West Bengal",
        country_name="India",
        country_code="IN",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-ALT-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Gtaq Field Recordings",
        description="Documentation of the Gtaq language.",
        location=location,
        version="1.0",
    )
    language = CollectionObjectLanguage.objects.create(
        display_name="Gtaq",
        name="Gtaq",
        iso_639_3_code="gaq",
        glottolog_code="gtaq1234",
    )
    alt_name = CollectionObjectLanguageAlternativeName.objects.create(value="Didei")
    language.alternative_names.add(alt_name)
    general_info.object_languages.add(language)

    # Search by alternative name should find the collection
    results = search_archives("Didei", use_stored_vectors=False)
    assert any(result.kind == "collection" and result.object_id == str(collection.pk) for result in results)


@pytest.mark.django_db
def test_bundle_search_matches_object_language_alternative_name():
    """Test that bundles can be found by searching for language alternative names."""
    collection = Collection.objects.create(identifier="COL-PARENT-ALTNAME")
    collection_location = CollectionLocation.objects.create(
        location_name="Mumbai",
        country_name="India",
        country_code="IN",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-PARENT-ALT",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Indian Languages Archive",
        description="Collection of Indian language recordings.",
        location=collection_location,
        version="1.0",
    )

    bundle = Bundle.objects.create(identifier="BND-ALTNAME-001")
    bundle_location = BundleLocation.objects.create(location_name="Mumbai")
    bundle_general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value="BID-ALT-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Chakravarti Gtaq Data 1",
        description="Language documentation recordings.",
        location=bundle_location,
        version="1.0",
    )
    bundle_language = BundleObjectLanguage.objects.create(
        display_name="Gtaq",
        name="Gtaq",
        iso_639_3_code="gaq",
        glottolog_code="gtaq1234",
    )
    alt_name = BundleObjectLanguageAlternativeName.objects.create(value="Didei")
    bundle_language.alternative_names.add(alt_name)
    bundle_general_info.object_languages.add(bundle_language)

    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )

    # Search by alternative name should find the bundle
    results = search_archives("Didei", use_stored_vectors=False)
    assert any(result.kind == "bundle" and result.object_id == str(bundle.pk) for result in results)


@pytest.mark.django_db
def test_search_excludes_bundle_when_policy_disallows_it(monkeypatch):
    collection = Collection.objects.create(identifier="COL-SEARCH-PARENT-001")
    collection_location = CollectionLocation.objects.create(
        location_name="Accra",
        country_name="Ghana",
        country_code="GH",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-SEARCH-PARENT-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Parent Search Collection",
        description="Parent collection for bundle search filtering.",
        location=collection_location,
        version="1.0",
    )

    bundle = Bundle.objects.create(identifier="BND-SEARCH-FILTER-001")
    bundle_location = BundleLocation.objects.create(location_name="Accra")
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value="BID-SEARCH-FILTER-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Filtered Search Bundle",
        description="Bundle hidden by exposure policy.",
        location=bundle_location,
        version="1.0",
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )

    def _can_list_in_search(self, user, obj):
        if isinstance(obj, Bundle) and obj.pk == bundle.pk:
            return False
        return True

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_list_in_search",
        _can_list_in_search,
    )

    results = search_archives("Filtered", use_stored_vectors=False)

    assert not any(
        result.kind == "bundle" and result.object_id == str(bundle.pk)
        for result in results
    )


@pytest.mark.django_db
def test_stored_vectors_search_matches_object_language_alternative_name():
    """Test that stored vectors include alternative names for search."""
    # Create collection with alternative language name
    collection = Collection.objects.create(identifier="COL-STORED-001")
    location = CollectionLocation.objects.create(
        location_name="Test Location",
        country_name="Test Country",
        country_code="TC",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-STORED-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Stored Vector Test Collection",
        description="Testing stored vectors with alternative names.",
        location=location,
        version="1.0",
    )
    language = CollectionObjectLanguage.objects.create(
        display_name="TestLang",
        name="TestLang",
        iso_639_3_code="tst",
        glottolog_code="test1234",
    )
    alt_name = CollectionObjectLanguageAlternativeName.objects.create(value="AlternativeTestName")
    language.alternative_names.add(alt_name)
    general_info.object_languages.add(language)

    # Rebuild search vectors
    rebuild_all_search_vectors()

    # Search using stored vectors should find the collection by alternative name
    results = search_archives("AlternativeTestName", use_stored_vectors=True)
    assert any(result.kind == "collection" and result.object_id == str(collection.pk) for result in results)


@pytest.mark.django_db
def test_typo_query_does_not_match_in_fts_only_mode():
    """Typo queries should not match once trigram fallback is removed."""
    collection = Collection.objects.create(identifier="COL-TRGM-001")
    location = CollectionLocation.objects.create(
        location_name="Korhogo",
        country_name="Ivory Coast",
        country_code="CI",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-TRGM-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Documentation of the Senufo languages.",
        location=location,
        version="1.0",
    )

    # Rebuild stored vectors so the stored-vector FTS path is used.
    rebuild_all_search_vectors()

    results = search_archives("senufu", use_stored_vectors=True)
    assert not any(
        result.kind == "collection" and result.object_id == str(collection.pk)
        for result in results
    )


@pytest.mark.django_db
def test_correct_search_uses_fts():
    """Correct search 'senufo' should match via FTS."""
    collection = Collection.objects.create(identifier="COL-FTS-001")
    location = CollectionLocation.objects.create(
        location_name="Korhogo",
        country_name="Ivory Coast",
        country_code="CI",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-FTS-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Documentation of the Senufo languages.",
        location=location,
        version="1.0",
    )

    # With stored vectors, FTS should find it directly
    rebuild_all_search_vectors()

    results = search_archives("senufo", use_stored_vectors=True)
    assert any(
        result.kind == "collection" and result.object_id == str(collection.pk)
        for result in results
    )


@pytest.mark.django_db
def test_short_query_uses_fts_prefix_matching():
    """Very short queries should still work through FTS prefix matching."""
    collection = Collection.objects.create(identifier="COL-SHORT-001")
    location = CollectionLocation.objects.create(
        location_name="Korhogo",
        country_name="Ivory Coast",
        country_code="CI",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-SHORT-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Documentation of the Senufo languages.",
        location=location,
        version="1.0",
    )

    rebuild_all_search_vectors()

    results = search_archives("se", use_stored_vectors=True)
    assert any(
        result.kind == "collection" and result.object_id == str(collection.pk)
        for result in results
    )


@pytest.mark.django_db
def test_collection_search_page_renders_highlighted_snippet(client):
    collection = Collection.objects.create(identifier="COL-PAGE-HL-001")
    location = CollectionLocation.objects.create(
        location_name="Korhogo",
        country_name="Ivory Coast",
        country_code="CI",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-PAGE-HL-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Senufo Language Archive",
        description="Documentation resources for Senufo speakers.",
        location=location,
        version="1.0",
    )

    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "se"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>" in page


@pytest.mark.django_db
def test_collection_list_has_no_advanced_search_jargon(client):
    response = client.get(reverse("explorer:collection_list"))
    assert response.status_code == 200
    page = response.content.decode("utf-8")

    assert "Advanced Search" not in page


@pytest.mark.django_db
def test_collection_search_page_renders_highlighted_bundle_snippet(client):
    collection = Collection.objects.create(identifier="COL-PARENT-001")
    collection_location = CollectionLocation.objects.create(
        location_name="Accra",
        country_name="Ghana",
        country_code="GH",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-PARENT-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Ghana Oral Histories",
        description="Source material for Ghanaian narratives.",
        location=collection_location,
        version="1.0",
    )

    bundle = Bundle.objects.create(identifier="BND-HL-001")
    bundle_location = BundleLocation.objects.create(location_name="Accra")
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value="BID-HL-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Evening Stories",
        description="Audio recordings of evening storytelling sessions.",
        location=bundle_location,
        version="1.0",
    )

    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "ev"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "BND-HL-001" in page
    assert "<mark>" in page


@pytest.mark.django_db
def test_collection_search_page_highlights_literal_fallback_snippet(client):
    collection = Collection.objects.create(identifier="COL-LIT-PAGE-001")
    location = CollectionLocation.objects.create(
        location_name="Bogota",
        country_name="Colombia",
        country_code="CO",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-LIT-PAGE-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Language Variety Archive",
        description="Documentation of language variety in Latin America.",
        location=location,
        version="1.0",
    )

    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "var"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>" in page


@pytest.mark.django_db
def test_collection_search_page_highlights_title_matches(client):
    collection = Collection.objects.create(identifier="COL-TITLE-HL-001")
    location = CollectionLocation.objects.create(
        location_name="Bogota",
        country_name="Colombia",
        country_code="CO",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="CID-TITLE-HL-001",
        id_type=IdentifierTypeChoices.DOI,
        display_title="Etymological Archive",
        description="Reference material.",
        location=location,
        version="1.0",
    )

    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "ety"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>Ety</mark>mological" in page
    assert "Matched in" in page
    assert "matched-in-row" in page


def test_render_search_snippet_allows_only_mark_tags():
    template = Template("{% load explorer_extras %}{{ snippet|render_search_snippet }}")
    rendered = template.render(
        Context({"snippet": "<mark>Senufo</mark><script>alert('x')</script>"})
    )

    assert "<mark>Senufo</mark>" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_dedup_prefers_highlighted_snippet_for_duplicate_results(monkeypatch):
    from lacos.explorer import search as search_module

    plain_result = search_module.SearchResult(
        kind="collection",
        object_id="obj-1",
        identifier="COL-001",
        title="Senufo Language Archive",
        description="Documentation resources for Senufo speakers.",
        highlight_snippet="Documentation resources for Senufo speakers.",
        matched_fields=("title",),
        url="/collections/obj-1/",
        rank=0.9,
    )
    highlighted_result = search_module.SearchResult(
        kind="collection",
        object_id="obj-1",
        identifier="COL-001",
        title="Senufo Language Archive",
        description="Documentation resources for Senufo speakers.",
        highlight_snippet="<mark>Senufo</mark> Language Archive",
        matched_fields=("title",),
        url="/collections/obj-1/",
        rank=0.2,
    )

    monkeypatch.setattr(
        search_module,
        "_search_collections",
        lambda query, term, use_stored_vectors=True: [plain_result, highlighted_result],
    )
    monkeypatch.setattr(search_module, "_search_bundles", lambda query, term, use_stored_vectors=True: [])

    results = search_module.search_archives("senufo", use_stored_vectors=True)
    assert len(results) == 1
    assert "<mark>" in results[0].highlight_snippet


def test_highlight_query_marks_literal_matches():
    template = Template("{% load explorer_extras %}{{ snippet|highlight_query:'ety' }}")
    rendered = template.render(
        Context({"snippet": "Documentation of language variety in Latin America."})
    )
    assert "<mark>ety</mark>" in rendered
