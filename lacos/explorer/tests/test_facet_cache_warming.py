"""Tests for deployment-time Explorer facet cache warming."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command

from lacos.explorer.facets import FacetService

INITIAL_COMPUTATION_COUNT = 2
REFRESHED_COMPUTATION_COUNT = 4


@pytest.mark.django_db
def test_warm_command_populates_both_facet_caches(monkeypatch):
    cache.clear()
    computations = {"count": 0}
    original_compute = FacetService._compute_facets  # noqa: SLF001

    def counting_compute(self, base_qs, selections):
        computations["count"] += 1
        return original_compute(self, base_qs, selections)

    monkeypatch.setattr(FacetService, "_compute_facets", counting_compute)
    stdout = StringIO()

    call_command("warm_explorer_facets", stdout=stdout)
    call_command("warm_explorer_facets", stdout=stdout)

    assert computations["count"] == INITIAL_COMPUTATION_COUNT
    assert "collection facets" in stdout.getvalue()
    assert "bundle facets" in stdout.getvalue()


@pytest.mark.django_db
def test_warm_command_refresh_recomputes_both_facet_caches(monkeypatch):
    cache.clear()
    computations = {"count": 0}
    original_compute = FacetService._compute_facets  # noqa: SLF001

    def counting_compute(self, base_qs, selections):
        computations["count"] += 1
        return original_compute(self, base_qs, selections)

    monkeypatch.setattr(FacetService, "_compute_facets", counting_compute)

    call_command("warm_explorer_facets", stdout=StringIO())
    call_command("warm_explorer_facets", refresh=True, stdout=StringIO())

    assert computations["count"] == REFRESHED_COMPUTATION_COUNT


@pytest.mark.django_db
def test_warm_command_propagates_facet_computation_errors(monkeypatch):
    cache.clear()
    error = RuntimeError("facet database failure")

    def fail_compute(self, base_qs, selections):
        raise error

    monkeypatch.setattr(FacetService, "_compute_facets", fail_compute)

    with pytest.raises(RuntimeError, match="facet database failure"):
        call_command("warm_explorer_facets", stdout=StringIO())
