# Storage Dashboard Lazy Loading Plan

## 1. Baseline Profiling
- Instrument `lacos/storage/views/dashboard_views.py` and `lacos/storage/services/bucket_service.py` to capture S3 call counts, payload sizes, and timing for:
  - Initial dashboard render (no HTMX)
  - First bucket tab click
  - Folder expansion (single and nested)
- Record results against representative buckets (small, medium, large) to quantify current overfetching.

## 2. Cache Audit
- Review `FolderStructureCacheService` usage in:
  - `BucketService.get_root_level_items`
  - `BucketService.get_folder_contents`
  - `CollectionService.list_bucket_contents`
- Document cache scope (per-process memory), TTL, invalidation paths, and identify misses (e.g., cache bypass on every root fetch).
- Evaluate whether Redis-backed caching is preferable for multi-worker deployments.

## 3. Pagination & Lazy Loading Design
- Revisit the removed pagination approach, noting which interfaces broke compatibility.
- Define new APIs for the service layer:
  - `CollectionService.list_bucket_contents(..., max_keys, continuation_token)`
  - Data structures to return items + `has_more` + `next_token`
- Ensure backward compatibility by providing legacy adapters where needed.

## 4. Dashboard Workflow Refactor
- Restructure `archivist_dashboard` to deliver metadata only (bucket list, active bucket) while deferring root structure to HTMX.
- Update HTMX endpoints (`dashboard_content`, `load_folder_contents`, `BucketContentHTMXView`) to:
  - Request paginated data
  - Propagate continuation tokens
  - Avoid re-rendering full bucket trees on partial updates.

## 5. Front-End Adjustments
- Modify `folder_structure_partial.html` and `folder_contents_partial.html` to show:
  - Loading indicators per folder
  - "Load more" controls when `has_more` is true
  - Graceful fallback when pagination is unavailable.
- Ensure the UX remains accessible and keyboard-friendly.

## 6. Enhanced Caching Strategy
- Expand the dedicated cache helper (`lacos.cache.core`) to handle folder listings alongside ACL payloads:
  - Redis-backed entries keyed by `(bucket, prefix)` with optional metadata (etag, last_modified).
  - No default TTL; rely on explicit invalidation via helper functions.
- Provide `StorageCache` utilities for uploads/deletes to invalidate affected prefixes immediately.
- Leave a feature flag (e.g. `STORAGE_FOLDER_CACHE_ENABLED`) to disable caching if needed.

## 7. Testing & Observability
- Add integration tests to `lacos/storage/tests/views/test_dashboard_views.py` and service tests for pagination behavior.
- Provide feature flags for rolling out the new logic (configurable defaults).
- Add structured logging/metrics to monitor S3 usage post-change.

## 8. Rollout Steps
- Stage implementation across multiple PRs:
  1. Instrumentation & baseline.
  2. Service-layer pagination with feature flag.
  3. HTMX + template updates.
  4. Cache upgrades.
  5. Cleanup & flag removal once stable.
- Communicate deployment considerations (cache warm-up, flag toggles, migration notes).
