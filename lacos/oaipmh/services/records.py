"""Repository-level OAI-PMH record retrieval helpers."""

from __future__ import annotations

from datetime import date
from typing import Optional

from .bundles import OAIPMHBundlesResult, fetch_bundle_records
from .collections import OAIPMHCollectionResult, fetch_collection_records

OAIResult = OAIPMHCollectionResult | OAIPMHBundlesResult


def fetch_repository_records(
    *,
    offset: int,
    from_date: Optional[date] = None,
    until_date: Optional[date] = None,
    limit: int,
    user=None,
) -> tuple[list[OAIResult], bool]:
    """Return a repository-wide page containing collection and bundle records."""

    fetch_limit = offset + limit + 1
    collection_records, collection_has_more = fetch_collection_records(
        offset=0,
        from_date=from_date,
        until_date=until_date,
        limit=fetch_limit,
        user=user,
    )
    bundle_records, bundle_has_more = fetch_bundle_records(
        offset=0,
        from_date=from_date,
        until_date=until_date,
        limit=fetch_limit,
        user=user,
    )

    combined_records: list[OAIResult] = [*collection_records, *bundle_records]
    page_end = offset + limit
    page = combined_records[offset:page_end]
    has_more = (
        len(combined_records) > page_end
        or collection_has_more
        or bundle_has_more
    )
    return page, has_more
