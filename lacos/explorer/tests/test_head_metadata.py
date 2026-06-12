from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
from http import HTTPStatus

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.base_indentifiers import AccessTypeChoices
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleLicense
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_publication_info import BundleCreator
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleAdditionalMetadataFile
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionLicense,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionRightsHolder,
)
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionKeyword
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_general_info import (
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import CollectionCreator
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
)
from lacos.storage.models.acl_permissions import ACLPermissions


class _HeadTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "meta" and "name" in attributes:
            self.meta.append(attributes)
        if tag == "link" and "rel" in attributes:
            self.links.append(attributes)


def _head_tags(response):
    parser = _HeadTagParser()
    parser.feed(response.content.decode("utf-8"))
    return parser


def _meta_values(parser, name: str) -> list[str]:
    return [meta["content"] for meta in parser.meta if meta.get("name") == name]


def _links(parser, rel: str) -> list[dict]:
    return [link for link in parser.links if link.get("rel") == rel]


def _create_collection(identifier="hdl:11341/test-head-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        geo_location="east=-65.5; north=-16.5",
        location_name="Chapare",
        region_name="Cochabamba",
        country_name="Bolivia",
        country_code="BO",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Head Metadata Collection",
        description="Collection description for Dublin Core.",
        recording_date=date(2013, 8, 28),
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(
        CollectionObjectLanguage.objects.create(
            display_name="Yuracaré",
            name="Yuracaré",
            iso_639_3_code="yuz",
            glottolog_code="yura1255",
        ),
    )
    general_info.keywords.add(CollectionKeyword.objects.create(value="Conversation"))
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


def _create_bundle(collection: Collection) -> Bundle:
    bundle = Bundle.objects.create(identifier="hdl:11341/test-head-bundle")
    location = BundleLocation.objects.create(
        location_name="Chapare",
        region_name="Cochabamba",
        country_name="Bolivia",
        country_code="BO",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=bundle.identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Family Problems Gladis and Arsenio",
        description="Session containing the three parts of the task.",
        recording_date=date(2013, 8, 28),
        version="1.0",
        location=location,
    )
    structural_info = BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_name="cmdi.xml",
        file_pid="hdl:11341/0000-0000-0000-2787",
        mime_type="application/xml",
        is_metadata_for=bundle.identifier,
    )
    structural_info.additional_metadata_files.add(metadata_file)
    media_resource = MediaResource.objects.create(
        file_name="audio.wav",
        file_pid="hdl:11341/00-0000-0000-0000-1C7E-9",
        mime_type="audio/x-wav",
        file_length="00:01:00",
    )
    resources = BundleResources.objects.create(bundle=bundle)
    resources.bundle_media_resources.add(media_resource)
    return bundle


def _allow_anonymous_read(obj) -> None:
    ACLPermissions.objects.update_or_create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        defaults={
            "ACL_file_bucket": "test-bucket",
            "ACL_file_key": "test/key",
            "permissions_data": [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}],
        },
    )


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://lac.uni-koeln.de")
def test_collection_detail_emits_dublin_core_and_signposting_head_links(client):
    collection = _create_collection()
    _allow_anonymous_read(collection)
    publication = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    publication.creators.add(
        CollectionCreator.objects.create(
            family_name="Gipper",
            given_name="Sonja",
            name_identifier="0000-0003-0972-1683",
            name_identifier_type="ORCID",
        ),
    )
    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=collection,
        access_level="public",
        availability_date=date(2024, 1, 1),
    )
    admin_info.licenses.add(
        CollectionLicense.objects.create(
            license_name="Copyright",
            license_identifier="https://en.wikipedia.org/wiki/Copyright",
            access=AccessTypeChoices.OPEN,
        ),
    )
    admin_info.rights_holders.add(
        CollectionRightsHolder.objects.create(rights_holder_name="Sonja Gipper"),
    )
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_name="collection.cmdi.xml",
        file_pid="hdl:11341/0000-0000-0000-2788",
        mime_type="application/xml",
        is_metadata_for=collection.identifier,
    )
    collection.get_structural_info.additional_metadata_files.add(metadata_file)

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.handle_path},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    parser = _head_tags(response)
    assert "Head Metadata Collection" in _meta_values(parser, "DC.title")
    assert "Gipper, Sonja" in _meta_values(parser, "DC.creator")
    assert "yuz" in _meta_values(parser, "DC.language")
    assert "Conversation" in _meta_values(parser, "DC.subject")
    assert "Sonja Gipper" in _meta_values(parser, "DCTERMS.rightsHolder")
    assert "2013-08-28" in _meta_values(parser, "DCTERMS.created")
    assert "2024" in _meta_values(parser, "DCTERMS.issued")
    assert "public" in _meta_values(parser, "DCTERMS.accessRights")
    assert {
        "rel": "cite-as",
        "href": "https://hdl.handle.net/11341/test-head-collection",
    } in parser.links
    assert {
        "rel": "author",
        "href": "https://orcid.org/0000-0003-0972-1683",
    } in parser.links
    assert {
        "rel": "DC.subject",
        "href": "https://glottolog.org/resource/languoid/id/yura1255",
    } in parser.links
    assert {
        "rel": "license",
        "href": "https://en.wikipedia.org/wiki/Copyright",
    } in parser.links
    assert any(
        link["href"] == "https://hdl.handle.net/11341/0000-0000-0000-2788"
        and link["type"] == "application/xml"
        for link in _links(parser, "describedby")
    )


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://lac.uni-koeln.de")
def test_bundle_detail_emits_dublin_core_and_signposting_for_files(client):
    collection = _create_collection("hdl:11341/test-head-parent")
    bundle = _create_bundle(collection)
    _allow_anonymous_read(bundle)
    publication = BundlePublicationInfo.objects.create(
        bundle=bundle,
        publication_year=2018,
        data_provider="LAC",
        identifier=bundle.identifier,
        identifier_type=IdentifierTypeChoices.HANDLE,
    )
    publication.creators.add(
        BundleCreator.objects.create(
            family_name="Gipper",
            given_name="Sonja",
            name_identifier="https://orcid.org/0000-0003-0972-1683",
            name_identifier_type="ORCID",
        ),
    )
    admin_info = BundleAdministrativeInfo.objects.create(
        bundle=bundle,
        access_level="restricted",
        availability_date=date(2018, 11, 29),
    )
    admin_info.licenses.add(
        BundleLicense.objects.create(
            license_name="Copyright",
            license_identifier="https://en.wikipedia.org/wiki/Copyright",
            access=AccessTypeChoices.REQUEST_REQUIRED,
        ),
    )

    response = client.get(
        reverse(
            "explorer:bundle_detail_by_handle",
            kwargs={"handle": bundle.handle_path},
        ),
    )

    assert response.status_code == HTTPStatus.OK
    parser = _head_tags(response)
    assert "Family Problems Gladis and Arsenio" in _meta_values(parser, "DC.title")
    assert "Gipper, Sonja" in _meta_values(parser, "DC.creator")
    assert "2013-08-28" in _meta_values(parser, "DCTERMS.created")
    assert "2018" in _meta_values(parser, "DCTERMS.issued")
    assert "public" in _meta_values(parser, "DCTERMS.accessRights")
    assert "application/xml" in _meta_values(parser, "DC.format")
    assert {
        "rel": "collection",
        "href": "https://hdl.handle.net/11341/test-head-parent",
    } in parser.links
    assert {
        "rel": "item",
        "href": "https://hdl.handle.net/11341/00-0000-0000-0000-1C7E-9",
        "type": "audio/x-wav",
    } in parser.links
    assert any(
        link["href"].endswith("/bundles/11341/test-head-bundle/metadata.xml")
        and link["type"] == "application/xml"
        for link in _links(parser, "describedby")
    )
    assert any(
        link["href"] == "https://hdl.handle.net/11341/0000-0000-0000-2787"
        and link["type"] == "application/xml"
        for link in _links(parser, "describedby")
    )
