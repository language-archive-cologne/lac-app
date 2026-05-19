import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_privacy_policy_mentions_saml_processing(client):
    response = client.get(reverse("privacy-policy"))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "Föderierte Anmeldung über Ihre Heimateinrichtung (SAML)" in body
    assert "Artikel 13 und 14 Datenschutzgrundverordnung" in body
    assert "Quelle der Daten" in body
    assert "eduPersonPrincipalName" in body
    assert "technische Kennung" in body
    assert "Art. 6 Abs. 1 lit. e DSGVO in Verbindung mit § 3 Hochschulgesetz NRW" in body
    assert "Zugriffssteuerung" in body


@pytest.mark.django_db
def test_about_page_uses_centered_team_grid(client):
    response = client.get(reverse("about"))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert 'class="team-grid" id="dept-01"' in body
    assert body.count('class="team-grid"') == 3
    assert "grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6" not in body
