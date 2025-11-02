"""Lightweight profiling utilities for storage dashboard interactions."""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

_state = threading.local()


def _get_stack() -> List["StorageProfilingSession"]:
    stack = getattr(_state, "stack", None)
    if stack is None:
        stack = []
        _state.stack = stack
    return stack


def get_current_session() -> Optional["StorageProfilingSession"]:
    stack = _get_stack()
    if not stack:
        return None
    return stack[-1]


@dataclass
class S3ListingMetrics:
    """Details about a single list_objects_v2 page fetch."""

    bucket: str
    prefix: str
    key_count: int
    size_bytes: int
    duration_ms: float
    continuation_token: Optional[str] = None
    is_truncated: bool = False
    cache_hit: Optional[bool] = None

    def to_log_data(self) -> Dict[str, Any]:
        data = {
            "bucket": self.bucket,
            "prefix": self.prefix or "",
            "key_count": self.key_count,
            "size_bytes": self.size_bytes,
            "duration_ms": round(self.duration_ms, 3),
            "continuation_token": self.continuation_token,
            "is_truncated": self.is_truncated,
        }
        if self.cache_hit is not None:
            data["cache_hit"] = self.cache_hit
        return data


@dataclass
class CacheEvent:
    """Cache usage details captured alongside S3 metrics."""

    bucket: str
    prefix: str
    event: str
    hit: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_log_data(self) -> Dict[str, Any]:
        payload = {
            "bucket": self.bucket,
            "prefix": self.prefix or "",
            "event": self.event,
            "hit": self.hit,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class StorageProfilingSession:
    """Accumulates metrics for the duration of a dashboard interaction."""

    label: str
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.perf_counter)
    s3_calls: List[S3ListingMetrics] = field(default_factory=list)
    cache_events: List[CacheEvent] = field(default_factory=list)

    def add_s3_call(self, metric: S3ListingMetrics) -> None:
        self.s3_calls.append(metric)

    def add_cache_event(self, event: CacheEvent) -> None:
        self.cache_events.append(event)

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.start_time) * 1000

    def _serialize(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "request_id": self.request_id,
            "duration_ms": round(self.elapsed_ms(), 3),
            "s3_call_count": len(self.s3_calls),
            "s3_calls": [metric.to_log_data() for metric in self.s3_calls],
            "cache_events": [event.to_log_data() for event in self.cache_events],
            "metadata": self.metadata,
        }

    def emit(self) -> None:
        payload = self._serialize()
        logger.info("storage_profiler: %s", json.dumps(payload, default=str))


@contextlib.contextmanager
def profiling_scope(label: str, *, request_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
    """
    Push a profiling session onto the thread-local stack for the duration
    of the managed block.

    Nested scopes coalesce metrics; only the outermost scope emits logs.
    """
    session = StorageProfilingSession(label=label, request_id=request_id, metadata=metadata or {})
    stack = _get_stack()
    stack.append(session)
    try:
        yield session
    finally:
        stack.pop()
        # Merge metrics into parent session if we are nested.
        if stack:
            parent = stack[-1]
            parent.s3_calls.extend(session.s3_calls)
            parent.cache_events.extend(session.cache_events)
        else:
            try:
                session.emit()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to emit storage profiling payload")


def record_s3_listing_page(
    *,
    bucket: str,
    prefix: str,
    key_count: int,
    size_bytes: int,
    duration_ms: float,
    continuation_token: Optional[str],
    is_truncated: bool,
    cache_hit: Optional[bool] = None,
) -> None:
    """Record metrics for one list_objects_v2 page, if a session is active."""
    session = get_current_session()
    if not session:
        return
    session.add_s3_call(
        S3ListingMetrics(
            bucket=bucket,
            prefix=prefix,
            key_count=key_count,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            continuation_token=continuation_token,
            is_truncated=is_truncated,
            cache_hit=cache_hit,
        )
    )


def record_cache_event(
    *,
    event: str,
    bucket: str,
    prefix: str,
    hit: bool,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Capture cache interactions for diagnostic logging."""
    session = get_current_session()
    if not session:
        return
    session.add_cache_event(
        CacheEvent(bucket=bucket, prefix=prefix, event=event, hit=hit, metadata=metadata or {})
    )


def summarise_calls(metrics: Iterable[S3ListingMetrics]) -> Dict[str, Any]:
    """Helper for tests to aggregate recorded S3 metrics."""
    metrics_list = list(metrics)
    return {
        "call_count": len(metrics_list),
        "total_bytes": sum(item.size_bytes for item in metrics_list),
        "total_keys": sum(item.key_count for item in metrics_list),
        "total_duration_ms": round(sum(item.duration_ms for item in metrics_list), 3),
    }
