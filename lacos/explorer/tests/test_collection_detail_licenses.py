from datetime import date
from uuid import uuid4

import pytest
from django.urls import reverse

from lacos.blam.models.base_indentifiers import AccessTypeChoices, IdentifierTypeChoices
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionLicense,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_repository import Collection


def _create_collection_with_licenses(
    *,
    identifier: str,
    md_license: str | None,
    md_license_uri: str | None,
    rights_license_name: str = "Copyright",
    rights_license_uri: str = "https://en.wikipedia.org/wiki/Copyright",
    create_rights_license: bool = True,
) -> Collection:
    collection = Collection.objects.create(identifier=identifier)

    location = CollectionLocation.objects.create(
        location_name="Test Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Test Collection",
        description="Collection description",
        version="1.0",
        location=location,
    )

    CollectionHeader.objects.create(
        collection=collection,
        md_creator="tester",
        md_self_link=f"https://example.org/metadata/{uuid4()}",
        md_profile="https://example.org/profile",
        md_license=md_license,
        md_license_uri=md_license_uri,
    )

    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=collection,
        access_level="public",
        availability_date=date.today(),
    )
    if create_rights_license:
        license_obj = CollectionLicense.objects.create(
            license_name=rights_license_name,
            license_identifier=rights_license_uri,
            access=AccessTypeChoices.OPEN,
        )
        admin_info.licenses.add(license_obj)

    return collection


@pytest.mark.django_db
def test_collection_detail_uses_administrative_license_badge_when_md_license_exists(client):
    collection = _create_collection_with_licenses(
        identifier="hdl:11341/test-collection-license",
        md_license="CC0",
        md_license_uri="https://creativecommons.org/public-domain/cc0/",
        rights_license_name="CC BY-SA 4.0",
        rights_license_uri="https://creativecommons.org/licenses/by-sa/4.0/",
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    content_licenses = list(response.context["content_licenses"])
    assert len(content_licenses) == 1
    assert content_licenses[0].license_name == "CC BY-SA 4.0"

    page = response.content.decode("utf-8")
    assert "CC BY-SA 4.0" in page
    assert "https://creativecommons.org/licenses/by-sa/4.0/" in page
    assert "License: CC0" not in page
    assert "https://creativecommons.org/public-domain/cc0/" not in page


@pytest.mark.django_db
def test_collection_detail_uses_administrative_license_when_md_license_missing(client):
    collection = _create_collection_with_licenses(
        identifier="hdl:11341/test-collection-no-md-license",
        md_license=None,
        md_license_uri=None,
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    content_licenses = list(response.context["content_licenses"])
    assert len(content_licenses) == 1
    assert content_licenses[0].license_name == "Copyright"
    page = response.content.decode("utf-8")
    assert "Copyright" in page
    assert "https://en.wikipedia.org/wiki/Copyright" in page
    assert "License: CC0" not in page


@pytest.mark.django_db
def test_collection_detail_does_not_fall_back_to_md_license_without_administrative_license(client):
    collection = _create_collection_with_licenses(
        identifier="hdl:11341/test-collection-md-license-only",
        md_license="CC0",
        md_license_uri="https://creativecommons.org/public-domain/cc0/",
        create_rights_license=False,
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    assert list(response.context["content_licenses"]) == []

    page = response.content.decode("utf-8")
    assert "License: CC0" not in page
    assert "https://creativecommons.org/public-domain/cc0/" not in page
