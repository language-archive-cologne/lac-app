from __future__ import annotations

import pytest

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleKeyword
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_general_info import BundleObjectLanguage
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleTopic
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionKeyword
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_general_info import CollectionObjectLanguage
from lacos.blam.models.collection.collection_publication_info import CollectionCreator
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.explorer.search import search_archives


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
