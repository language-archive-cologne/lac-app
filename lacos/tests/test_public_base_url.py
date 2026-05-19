from http import HTTPStatus

import pytest
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
)


def _create_collection(identifier: str = "hdl:11341/test-public-base") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Public Base Test Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Public Base Collection",
        description="Collection for public base URL tests",
        version="1.0",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


@pytest.mark.django_db
@override_settings(
    PUBLIC_BASE_URL="https://lac.uni-koeln.de",
    ALLOWED_HOSTS=["lacos.uni-koeln.de"],
)
def test_default_seo_uses_public_base_url_instead_of_request_host(client):
    response = client.get("/", HTTP_HOST="lacos.uni-koeln.de")

    assert response.status_code == HTTPStatus.OK
    body = response.content.decode("utf-8")
    assert '<link rel="canonical" href="https://lac.uni-koeln.de/"' in body
    assert '<meta property="og:url" content="https://lac.uni-koeln.de/"' in body
    assert '<meta name="twitter:url" content="https://lac.uni-koeln.de/"' in body


@pytest.mark.django_db
@override_settings(
    PUBLIC_BASE_URL="https://lac.uni-koeln.de",
    ALLOWED_HOSTS=["lacos.uni-koeln.de"],
)
def test_collection_detail_public_urls_use_public_base_url(client):
    collection = _create_collection()

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.handle_path},
        ),
        HTTP_HOST="lacos.uni-koeln.de",
    )

    assert response.status_code == HTTPStatus.OK
    body = response.content.decode("utf-8")
    collection_url = f"https://lac.uni-koeln.de/collections/{collection.handle_path}/"
    assert f'<link rel="canonical" href="{collection_url}"' in body
    assert f'data-copy-text="{collection_url}"' in body
    assert '"url": "https://lac.uni-koeln.de"' in body
    assert '"license": "https://lac.uni-koeln.de/privacy-policy/"' in body


@override_settings(PUBLIC_BASE_URL="https://lac.uni-koeln.de")
@pytest.mark.django_db
def test_robots_and_llms_use_public_base_url(client):
    robots_response = client.get("/robots.txt")
    llms_response = client.get("/llms.txt")

    assert robots_response.status_code == HTTPStatus.OK
    assert llms_response.status_code == HTTPStatus.OK
    assert (
        "Sitemap: https://lac.uni-koeln.de/sitemap.xml"
        in robots_response.content.decode("utf-8")
    )
    llms_body = llms_response.content.decode("utf-8")
    assert "- [Collections](/collections/):" in llms_body
    assert "- Website: https://lac.uni-koeln.de" in llms_body
