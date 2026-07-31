"""Repository-level OAI-PMH record retrieval helpers."""

from __future__ import annotations

from datetime import date
from typing import Optional

from .bundles import OAIPMHBundlesResult, fetch_bundle_records, has_bundle_records
from .collections import (
    OAIPMHCollectionResult,
    count_collection_records,
    fetch_collection_records,
)

OAIResult = OAIPMHCollectionResult | OAIPMHBundlesResult


def fetch_repository_records(
    *,
    offset: int,
    from_date: Optional[date] = None,
    until_date: Optional[date] = None,
    limit: int,
    user=None,
) -> tuple[list[OAIResult], bool]:
    """Return a repository-wide page containing collection and bundle records.

    The combined sequence is all collections followed by all bundles, so the
    repository offset maps directly onto the two sub-sequences and each page
    only materializes the records it returns.
    """

    total_collections = count_collection_records(
        from_date=from_date,
        until_date=until_date,
        user=user,
    )

    page: list[OAIResult] = []
    if offset < total_collections:
        collection_page, _ = fetch_collection_records(
            offset=offset,
            from_date=from_date,
            until_date=until_date,
            limit=min(limit, total_collections - offset),
            user=user,
        )
        page.extend(collection_page)

    bundle_offset = max(0, offset - total_collections)
    bundle_limit = offset + limit - max(offset, total_collections)
    if bundle_limit > 0:
        bundle_page, has_more = fetch_bundle_records(
            offset=bundle_offset,
            from_date=from_date,
            until_date=until_date,
            limit=bundle_limit,
            user=user,
        )
        page.extend(bundle_page)
    else:
        has_more = offset + limit < total_collections or (
            offset + limit == total_collections
            and has_bundle_records(from_date=from_date, until_date=until_date, user=user)
        )
    return page, has_more
