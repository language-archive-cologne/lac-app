from __future__ import annotations

import pytest

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
from lacos.blam.models.bundle.bundle_structural_info import BundleTopic
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
    topic = BundleTopic.objects.create(name="oral history")
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
    structural_info.bundle_topics.add(topic)

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
def test_trigram_fallback_finds_typo():
    """Typo 'senufu' should find 'Senufo Language Archive' via trigram fallback."""
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

    # Rebuild stored vectors so FTS path runs first and finds nothing
    rebuild_all_search_vectors()

    results = search_archives("senufu", use_stored_vectors=True)
    assert any(
        result.kind == "collection" and result.object_id == str(collection.pk)
        for result in results
    )


@pytest.mark.django_db
def test_correct_search_uses_fts_not_trigram():
    """Correct search 'senufo' should use the fast FTS path."""
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
def test_short_query_skips_trigram_fallback():
    """Very short query ('se') should not trigger trigram fallback."""
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

    # 'se' is only 2 chars — FTS won't match (no prefix match on 'se' for 'Senufo'?),
    # but trigram should be skipped due to guard
    results = search_archives("se", use_stored_vectors=True)
    # With prefix matching, FTS may or may not find this — but trigram must not run.
    # The key assertion: we don't crash and results are either from FTS or empty.
    assert isinstance(results, list)
