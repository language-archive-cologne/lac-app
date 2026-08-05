"""Query-scaling regressions for explorer metadata exports."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_general_info import BundleObjectLanguage
from lacos.blam.models.bundle.bundle_general_info import (
    BundleObjectLanguageAlternativeName,
)
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResourceAnnotation
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_general_info import (
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionObjectLanguageAlternativeName,
)
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
)

HTTP_OK = 200
COLLECTION_JSONLD_QUERY_BUDGET = 26
BUNDLE_JSONLD_QUERY_BUDGET = 32
BUNDLE_XML_QUERY_BUDGET = 37
COLLECTION_XML_QUERY_BUDGET = 32


def _make_collection(identifier: str, *, language_count: int = 1) -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    CollectionHeader.objects.create(
        collection=collection,
        md_creator="Query profiler",
        md_self_link=identifier,
        md_profile="https://example.test/profile",
    )
    location = CollectionLocation.objects.create(
        country_name="Germany",
        country_code="DE",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=f"Collection {identifier}",
        location=location,
    )
    for index in range(language_count):
        language = CollectionObjectLanguage.objects.create(
            display_name=f"Collection language {index}",
            name=f"Collection language {index}",
            iso_639_3_code=f"c{index:02d}",
        )
        alternative_name = CollectionObjectLanguageAlternativeName.objects.create(
            value=f"Collection alternative {index}",
        )
        language.alternative_names.add(alternative_name)
        general_info.object_languages.add(language)
    CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2026,
        data_provider="LAC",
    )
    return collection


def _make_bundle(
    identifier: str,
    collection: Collection,
    *,
    language_count: int = 1,
    written_resource_count: int = 0,
) -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    BundleHeader.objects.create(
        bundle=bundle,
        md_creator="Query profiler",
        md_self_link=identifier,
        md_profile="https://example.test/profile",
    )
    location = BundleLocation.objects.create(
        country_name="Germany",
        country_code="DE",
    )
    general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=f"Bundle {identifier}",
        location=location,
    )
    for index in range(language_count):
        language = BundleObjectLanguage.objects.create(
            display_name=f"Bundle language {identifier}-{index}",
            name=f"Bundle language {identifier}-{index}",
            iso_639_3_code=f"b{index:02d}",
        )
        alternative_name = BundleObjectLanguageAlternativeName.objects.create(
            value=f"Bundle alternative {identifier}-{index}",
        )
        language.alternative_names.add(alternative_name)
        general_info.object_languages.add(language)
    BundlePublicationInfo.objects.create(
        bundle=bundle,
        publication_year=2026,
        data_provider="LAC",
        identifier=identifier,
        identifier_type=IdentifierTypeChoices.HANDLE,
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    resources = BundleResources.objects.create(bundle=bundle)
    for index in range(written_resource_count):
        resource = WrittenResource.objects.create(
            file_name=f"annotation-{index}.eaf",
            file_pid=f"https://hdl.example/{bundle.pk}/{index}",
            mime_type="text/x-eaf+xml",
        )
        WrittenResourceAnnotation.objects.create(
            written_resource=resource,
            is_annotation_of=f"https://hdl.example/media/{bundle.pk}/{index}",
        )
        resources.bundle_written_resources.add(resource)
    return bundle


def _capture_get(client, url: str) -> CaptureQueriesContext:
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
        assert response.status_code == HTTP_OK
        _ = response.content
    return captured


def _direct_select_count(captured: CaptureQueriesContext, model) -> int:
    quoted_table = connection.ops.quote_name(model._meta.db_table)  # noqa: SLF001
    return sum(
        f"FROM {quoted_table}" in query["sql"] for query in captured.captured_queries
    )


@pytest.mark.django_db
def test_collection_jsonld_queries_do_not_grow_with_language_count(
    client,
    django_user_model,
):
    client.force_login(
        django_user_model.objects.create_user(username="collection-export"),
    )
    small = _make_collection("hdl:test/query-collection-small", language_count=1)
    large = _make_collection("hdl:test/query-collection-large", language_count=6)

    assert (
        client.get(f"/collections/{small.identifier}/metadata.jsonld").status_code
        == HTTP_OK
    )
    small_queries = _capture_get(
        client, f"/collections/{small.identifier}/metadata.jsonld",
    )
    large_queries = _capture_get(
        client, f"/collections/{large.identifier}/metadata.jsonld",
    )

    assert len(large_queries) == len(small_queries)
    assert len(large_queries) <= COLLECTION_JSONLD_QUERY_BUDGET
    assert _direct_select_count(large_queries, CollectionGeneralInfo) == 1


@pytest.mark.django_db
def test_bundle_jsonld_queries_do_not_grow_with_language_count(
    client,
    django_user_model,
):
    client.force_login(django_user_model.objects.create_user(username="bundle-export"))
    collection = _make_collection("hdl:test/query-bundle-parent")
    small = _make_bundle("hdl:test/query-bundle-small", collection, language_count=1)
    large = _make_bundle("hdl:test/query-bundle-large", collection, language_count=6)

    assert (
        client.get(f"/bundles/{small.identifier}/metadata.jsonld").status_code
        == HTTP_OK
    )
    small_queries = _capture_get(client, f"/bundles/{small.identifier}/metadata.jsonld")
    large_queries = _capture_get(client, f"/bundles/{large.identifier}/metadata.jsonld")

    assert len(large_queries) == len(small_queries)
    assert len(large_queries) <= BUNDLE_JSONLD_QUERY_BUDGET
    assert _direct_select_count(large_queries, BundleGeneralInfo) == 1


@pytest.mark.django_db
def test_bundle_xml_queries_do_not_grow_with_written_resource_count(
    client,
    django_user_model,
):
    client.force_login(
        django_user_model.objects.create_user(username="bundle-xml-export"),
    )
    collection = _make_collection("hdl:test/query-bundle-xml-parent")
    small = _make_bundle(
        "hdl:test/query-bundle-xml-small",
        collection,
        written_resource_count=1,
    )
    large = _make_bundle(
        "hdl:test/query-bundle-xml-large",
        collection,
        written_resource_count=6,
    )

    assert (
        client.get(f"/bundles/{small.identifier}/metadata.xml").status_code
        == HTTP_OK
    )
    small_queries = _capture_get(client, f"/bundles/{small.identifier}/metadata.xml")
    large_queries = _capture_get(client, f"/bundles/{large.identifier}/metadata.xml")

    assert len(large_queries) == len(small_queries)
    assert len(large_queries) <= BUNDLE_XML_QUERY_BUDGET
    assert _direct_select_count(large_queries, BundleResources) == 1


@pytest.mark.django_db
def test_collection_xml_fetches_member_bundles_once(client, django_user_model):
    client.force_login(
        django_user_model.objects.create_user(username="collection-xml-export"),
    )
    collection = _make_collection("hdl:test/query-collection-members")
    for index in range(6):
        _make_bundle(f"hdl:test/query-member-{index}", collection)

    captured = _capture_get(
        client, f"/collections/{collection.identifier}/metadata.xml",
    )

    assert len(captured) <= COLLECTION_XML_QUERY_BUDGET
    assert _direct_select_count(captured, BundleStructuralInfo) == 1
