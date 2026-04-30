import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_identify(client):
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "Identify"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<Identify>" in body
    assert "<repositoryName>" in body
    assert "<adminEmail>lac-helpdesk@uni-koeln.de</adminEmail>" in body
    assert "support@example.com" not in body


@pytest.mark.django_db
def test_list_metadata_formats(client):
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "ListMetadataFormats"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "oai_dc" in body
    assert "olac" in body
    assert "schema_org" in body


@pytest.mark.django_db
def test_list_sets(client):
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "ListSets"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "collections" in body
    assert "bundles" in body


@pytest.mark.django_db
def test_list_records_without_data_returns_error(client):
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "oai_dc"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "noRecordsMatch" in body
