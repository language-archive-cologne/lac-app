"""Tests for repository-wide OAI-PMH pagination (collections + bundles).

Repository pages are composed from two ordered sub-sequences: all
collections first, then all bundles. Offsets must map directly onto that
combined sequence, and a page must never materialize records outside the
window it returns.
"""

import pytest

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.oaipmh.identifiers import build_oai_identifier
from lacos.oaipmh.services import fetch_repository_records
from lacos.oaipmh.services import records as records_module


def _make(collections: int, bundles: int) -> tuple[list[Collection], list[Bundle]]:
    cols = [
        Collection.objects.create(identifier=f"hdl:test/repo-col-{i:02d}")
        for i in range(collections)
    ]
    buns = [
        Bundle.objects.create(identifier=f"hdl:test/repo-bun-{i:02d}")
        for i in range(bundles)
    ]
    return cols, buns


def _walk(limit: int) -> list[str]:
    harvested: list[str] = []
    offset = 0
    for _ in range(30):
        results, has_more = fetch_repository_records(offset=offset, limit=limit)
        harvested.extend(result.identifier for result in results)
        if not has_more:
            return harvested
        offset += limit
    raise AssertionError("pagination did not terminate")


@pytest.mark.django_db
def test_walk_yields_collections_then_bundles_exactly_once():
    cols, buns = _make(5, 7)
    harvested = _walk(limit=3)
    expected = [build_oai_identifier(r.identifier) for r in [*cols, *buns]]
    assert harvested == expected


@pytest.mark.django_db
def test_boundary_page_straddles_collections_and_bundles():
    cols, buns = _make(5, 4)
    results, has_more = fetch_repository_records(offset=3, limit=4)
    assert [r.identifier for r in results] == [
        build_oai_identifier(r.identifier) for r in [*cols[3:5], *buns[0:2]]
    ]
    assert has_more is True


@pytest.mark.django_db
def test_page_ending_exactly_at_last_collection_still_has_more():
    _make(4, 2)
    results, has_more = fetch_repository_records(offset=0, limit=4)
    assert len(results) == 4
    assert has_more is True


@pytest.mark.django_db
def test_no_bundles_ends_after_collections():
    _make(4, 0)
    results, has_more = fetch_repository_records(offset=0, limit=4)
    assert len(results) == 4
    assert has_more is False


@pytest.mark.django_db
def test_no_collections_pages_through_bundles():
    _, buns = _make(0, 5)
    harvested = _walk(limit=2)
    assert harvested == [build_oai_identifier(r.identifier) for r in buns]


@pytest.mark.django_db
def test_offset_past_end_returns_empty_page():
    _make(2, 2)
    results, has_more = fetch_repository_records(offset=10, limit=5)
    assert results == []
    assert has_more is False


@pytest.mark.django_db
def test_deep_page_fetches_only_its_own_window(monkeypatch):
    """A page must not re-fetch the whole prefix: no sub-fetch may be asked
    for more records than the page itself returns."""
    _make(8, 8)
    calls: list[tuple[str, int, int]] = []
    real_col = records_module.fetch_collection_records
    real_bun = records_module.fetch_bundle_records

    def spy_col(**kwargs):
        calls.append(("collections", kwargs["offset"], kwargs["limit"]))
        return real_col(**kwargs)

    def spy_bun(**kwargs):
        calls.append(("bundles", kwargs["offset"], kwargs["limit"]))
        return real_bun(**kwargs)

    monkeypatch.setattr(records_module, "fetch_collection_records", spy_col)
    monkeypatch.setattr(records_module, "fetch_bundle_records", spy_bun)

    results, has_more = fetch_repository_records(offset=10, limit=3)
    assert len(results) == 3
    assert has_more is True
    assert calls, "expected the repository fetch to delegate to sub-fetchers"
    for _kind, _offset, limit in calls:
        assert limit <= 3
