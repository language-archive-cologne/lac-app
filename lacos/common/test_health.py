"""Readiness endpoint tests."""

from __future__ import annotations

import pytest

HTTP_OK = 200
HTTP_SERVICE_UNAVAILABLE = 503


@pytest.mark.django_db
def test_readiness_reports_database_and_cache_health(client):
    response = client.get("/health/ready/")

    assert response.status_code == HTTP_OK
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "cache": "ok"},
    }


@pytest.mark.django_db
def test_readiness_returns_503_when_database_is_unavailable(client, monkeypatch):
    from lacos.common import health

    monkeypatch.setattr(
        health,
        "check_database",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    response = client.get("/health/ready/")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    assert response.json()["checks"] == {"database": "failed", "cache": "ok"}


@pytest.mark.django_db
def test_readiness_returns_503_when_cache_is_unavailable(client, monkeypatch):
    from lacos.common import health

    monkeypatch.setattr(
        health,
        "check_cache",
        lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")),
    )

    response = client.get("/health/ready/")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    assert response.json()["checks"] == {"database": "ok", "cache": "failed"}
