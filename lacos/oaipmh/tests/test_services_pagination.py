"""Pagination consistency tests for the OAI-PMH record fetchers.

The exposure policy participates in pagination at two levels: queryset
filters define the sequence that offsets index into, while per-object
checks act as a final guard. These tests pin down that neither level can
corrupt offsets or ``has_more``.
"""

import pytest

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.oaipmh.identifiers import build_oai_identifier
from lacos.oaipmh.services import fetch_bundle_records, fetch_collection_records
from lacos.storage.services.exposure_policy_service import ExposurePolicyService


def _make_collections(count: int) -> list[Collection]:
    return [
        Collection.objects.create(identifier=f"hdl:test/pag-col-{i:02d}")
        for i in range(count)
    ]


def _make_bundles(count: int) -> list[Bundle]:
    return [
        Bundle.objects.create(identifier=f"hdl:test/pag-bun-{i:02d}")
        for i in range(count)
    ]


def _walk(fetch_fn, limit: int) -> list[str]:
    """Harvest all pages like an OAI client and return local identifiers."""
    harvested: list[str] = []
    offset = 0
    for _ in range(20):
        results, has_more = fetch_fn(offset=offset, limit=limit)
        harvested.extend(result.identifier for result in results)
        if not has_more:
            return harvested
        offset += limit
    raise AssertionError("pagination did not terminate")


FETCHERS = [
    pytest.param(fetch_collection_records, _make_collections, id="collections"),
    pytest.param(fetch_bundle_records, _make_bundles, id="bundles"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("fetch_fn", "make_records"), FETCHERS)
def test_unfiltered_walk_yields_every_record_once(fetch_fn, make_records):
    records = make_records(5)
    harvested = _walk(fetch_fn, limit=2)
    assert len(harvested) == 5
    assert len(set(harvested)) == 5
    assert set(harvested) == {build_oai_identifier(r.identifier) for r in records}


@pytest.mark.django_db
@pytest.mark.parametrize(("fetch_fn", "make_records"), FETCHERS)
def test_queryset_filter_defines_pagination_sequence(
    fetch_fn, make_records, monkeypatch
):
    """Records excluded by the channel queryset filter must not consume
    offset positions or distort has_more."""
    records = make_records(5)
    excluded = records[1]

    def _filter(self, user, queryset, *, channel):
        return queryset.exclude(pk=excluded.pk)

    monkeypatch.setattr(ExposurePolicyService, "filter_collection_queryset", _filter)
    monkeypatch.setattr(ExposurePolicyService, "filter_bundle_queryset", _filter)

    harvested = _walk(fetch_fn, limit=2)
    assert len(harvested) == 4
    assert len(set(harvested)) == 4
    assert build_oai_identifier(excluded.identifier) not in harvested


@pytest.mark.django_db
@pytest.mark.parametrize(("fetch_fn", "make_records"), FETCHERS)
def test_per_object_deny_does_not_corrupt_has_more(fetch_fn, make_records, monkeypatch):
    """A per-object deny may hide its record but must not truncate the
    harvest: pages after the denied record must still be reachable."""
    records = make_records(5)
    denied = records[1]

    def _can_harvest(self, user, obj):
        return obj.pk != denied.pk

    monkeypatch.setattr(ExposurePolicyService, "can_harvest_via_oai", _can_harvest)

    harvested = _walk(fetch_fn, limit=2)
    assert len(harvested) == 4
    assert len(set(harvested)) == 4
    assert build_oai_identifier(denied.identifier) not in harvested


@pytest.mark.django_db
@pytest.mark.parametrize(("fetch_fn", "make_records"), FETCHERS)
def test_has_more_false_on_exact_page_boundary(fetch_fn, make_records):
    make_records(4)
    results, has_more = fetch_fn(offset=2, limit=2)
    assert len(results) == 2
    assert has_more is False
