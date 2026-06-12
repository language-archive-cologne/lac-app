import json
import re
from html.parser import HTMLParser

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
)
from lacos.explorer.structured_data import serialize_json_ld
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.exposure_policy_service import ExposurePolicyService


class _JsonLdScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_json_ld = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        attributes = dict(attrs)
        self._in_json_ld = attributes.get("type") == "application/ld+json"
        if self._in_json_ld:
            self.scripts.append("")

    def handle_data(self, data):
        if self._in_json_ld:
            self.scripts[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_json_ld = False


def _json_ld_scripts(body: str) -> list[str]:
    parser = _JsonLdScriptParser()
    parser.feed(body)
    return parser.scripts


def _default_meta_description(body: str) -> str:
    match = re.search(r'<meta name="description" content="([^"]+)"', body)
    assert match
    return match.group(1)


def _create_collection(identifier: str = "discoverability-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Discoverability Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Discoverability Collection",
        description="Discoverability Collection Description",
        version="1.0",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


def _create_bundle(collection: Collection, identifier: str = "discoverability-bundle") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Discoverability Bundle Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Discoverability Bundle",
        description="Discoverability Bundle Description",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _store_acl(obj, rules):
    ct = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.create(
        content_type=ct,
        object_id=obj.pk,
        ACL_file_bucket="test-bucket",
        ACL_file_key="test/key",
        permissions_data=rules,
    )


@pytest.mark.django_db
@override_settings(
    ALLOWED_HOSTS=["lac.uni-koeln.de"],
    PUBLIC_BASE_URL="https://lac.uni-koeln.de",
)
def test_catalogue_root_emits_schema_org_data_catalog_json_ld(client):
    response = client.get("/", HTTP_HOST="lac.uni-koeln.de")

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    scripts = _json_ld_scripts(body)
    assert len(scripts) == 1

    payload = json.loads(scripts[0])
    catalog, organization = payload["@graph"]

    assert payload["@context"] == "https://schema.org/"
    assert catalog["@type"] == "DataCatalog"
    assert catalog["@id"] == "https://lac.uni-koeln.de/#catalog"
    assert catalog["url"] == "https://lac.uni-koeln.de/"
    assert catalog["description"] == _default_meta_description(body)
    assert catalog["publisher"] == {"@id": "https://lac.uni-koeln.de/#org"}
    assert catalog["provider"] == {"@id": "https://lac.uni-koeln.de/#org"}
    assert organization["@type"] == "Organization"
    assert organization["identifier"]["propertyID"] == "re3data"
    assert organization["identifier"]["url"] == "https://doi.org/10.17616/R3JV4W"


@pytest.mark.django_db
@override_settings(
    ALLOWED_HOSTS=["lac.uni-koeln.de"],
    EXPLORER_COLLECTIONS_PAGE_SIZE=1,
    PUBLIC_BASE_URL="https://lac.uni-koeln.de",
)
def test_paginated_catalogue_root_emits_schema_org_data_catalog_json_ld(client):
    _create_collection("discoverability-paginated-catalogue-1")
    _create_collection("discoverability-paginated-catalogue-2")

    response = client.get("/", {"page": 2}, HTTP_HOST="lac.uni-koeln.de")

    assert response.status_code == 200
    payload = json.loads(_json_ld_scripts(response.content.decode("utf-8"))[0])
    assert payload["@graph"][0]["@id"] == "https://lac.uni-koeln.de/#catalog"


def test_json_ld_serialization_escapes_script_breaking_less_than_signs():
    serialized = serialize_json_ld({"value": "</script><script>alert(1)</script>"})

    assert "<" not in serialized
    assert json.loads(serialized) == {"value": "</script><script>alert(1)</script>"}


@pytest.mark.django_db
def test_sitemap_includes_restricted_metadata_pages(client):
    collection = _create_collection("discoverability-restricted-collection")
    bundle = _create_bundle(collection, "discoverability-restricted-bundle")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    response = client.get(reverse("django.contrib.sitemaps.views.sitemap"))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert collection.handle_path in body
    assert bundle.handle_path in body


@pytest.mark.django_db
def test_sitemap_excludes_items_when_policy_disallows_them(client, monkeypatch):
    collection = _create_collection("discoverability-sitemap-filtered-collection")
    bundle = _create_bundle(collection, "discoverability-sitemap-filtered-bundle")

    def _can_appear_in_sitemap(self, user, obj):
        if getattr(obj, "identifier", None) in {collection.identifier, bundle.identifier}:
            return False
        return True

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_appear_in_sitemap",
        _can_appear_in_sitemap,
    )

    response = client.get(reverse("django.contrib.sitemaps.views.sitemap"))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert collection.handle_path not in body
    assert bundle.handle_path not in body


@pytest.mark.django_db
def test_oai_list_identifiers_includes_restricted_collection_metadata(client):
    collection = _create_collection("discoverability-oai-collection")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListIdentifiers", "metadataPrefix": "oai_dc", "set": "collections"},
    )

    assert response.status_code == 200
    assert f"oai:lacos:{collection.identifier}" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_oai_excludes_collection_when_policy_disallows_harvest(client, monkeypatch):
    collection = _create_collection("discoverability-oai-filtered-collection")

    def _can_harvest_via_oai(self, user, obj):
        if getattr(obj, "identifier", None) == collection.identifier:
            return False
        return True

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_harvest_via_oai",
        _can_harvest_via_oai,
    )

    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListIdentifiers", "metadataPrefix": "oai_dc", "set": "collections"},
    )

    assert response.status_code == 200
    assert f"oai:lacos:{collection.identifier}" not in response.content.decode("utf-8")
