from http import HTTPStatus

import pytest
from django.urls import reverse


def test_api_docs_accessible_by_admin(admin_client):
    url = reverse("api-docs")
    response = admin_client.get(url)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_api_docs_accessible_by_anonymous_users(client):
    url = reverse("api-docs")
    response = client.get(url)
    assert response.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_api_docs_use_self_hosted_swagger_assets(client):
    url = reverse("api-docs")
    response = client.get(url)
    body = response.content.decode("utf-8")

    assert response.status_code == HTTPStatus.OK
    assert "cdn.jsdelivr.net" not in body
    assert "/static/vendor/swagger-ui/swagger-ui.css" in body
    assert "/static/vendor/swagger-ui/swagger-ui-bundle.js" in body
    assert "/static/vendor/swagger-ui/swagger-ui-standalone-preset.js" in body
    assert "/static/vendor/swagger-ui/favicon-32x32.png" in body


def test_api_schema_generated_successfully(admin_client):
    url = reverse("api-schema")
    response = admin_client.get(url)
    assert response.status_code == HTTPStatus.OK
