import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.views.download_utils import check_resource_authorization


def _request():
    request = RequestFactory().get("/storage/download/")
    request.user = AnonymousUser()
    request.META["REMOTE_ADDR"] = "127.0.0.1"
    return request


def _create_collection(identifier: str = "download-utils-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Download Utils Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Download Utils Collection",
        description="Download Utils Collection Description",
        version="1.0",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


@pytest.mark.django_db
def test_check_resource_authorization_denies_unresolved_location():
    resource_content_type = ContentType.objects.get_for_model(CollectionAdditionalMetadataFile)
    S3ResourceLocation.objects.create(
        resource_pid="hdl:test/orphan-download",
        s3_bucket="lacos-production",
        s3_key="orphan/file.xml",
        mime_type="application/xml",
        content_type=resource_content_type,
        object_id=str(uuid.uuid4()),
    )

    error = check_resource_authorization(_request(), "lacos-production", "orphan/file.xml")

    assert error == "Access denied"


@pytest.mark.django_db
def test_check_resource_authorization_allows_public_collection_metadata_file():
    collection = _create_collection()
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/public-download-metadata",
        file_name="public.xml",
        file_description="Public metadata",
        mime_type="application/xml",
    )
    collection.structural_info.first().additional_metadata_files.add(metadata_file)
    content_type = ContentType.objects.get_for_model(metadata_file)
    S3ResourceLocation.objects.create(
        resource_pid=metadata_file.file_pid,
        s3_bucket="lacos-production",
        s3_key="collection/public.xml",
        mime_type=metadata_file.mime_type,
        content_type=content_type,
        object_id=str(metadata_file.pk),
    )

    error = check_resource_authorization(_request(), "lacos-production", "collection/public.xml")

    assert error is None
