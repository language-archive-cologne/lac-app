"""Resource budgets and count-free pagination for interactive search."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.db import DatabaseError
from django.db import connection
from django.db import transaction
from django.http import Http404
from django.http import HttpResponse

from lacos.explorer.facets import FacetCacheBusyError
from lacos.explorer.facets import FacetSelectionLimitError
from lacos.explorer.public_search.service import is_anonymous_public_search
from lacos.explorer.public_search.service import public_search_unavailable_response
from lacos.explorer.public_search.store import PublicSearchIndexError

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

SEARCH_MAX_QUERY_LENGTH = 200
SEARCH_MAX_PAGE = 400
SEARCH_RETRY_AFTER_SECONDS = 5
POSTGRES_QUERY_CANCELED = "57014"
NO_NEXT_PAGE_MESSAGE = "This page has no next page."
NO_PREVIOUS_PAGE_MESSAGE = "This page has no previous page."
NON_NUMERIC_PAGE_MESSAGE = "Page is not a number."
NON_POSITIVE_PAGE_MESSAGE = "Page number must be positive."
EMPTY_PAGE_MESSAGE = "That page contains no results."


class SearchPageLimitError(ValueError):
    """Raised when offset pagination exceeds its supported request budget."""


@dataclass(frozen=True)
class CountlessPaginator:
    """Minimal paginator metadata that never evaluates an exact count."""

    per_page: int


@dataclass(frozen=True)
class CountlessPage:
    """One page plus knowledge derived from fetching one extra row."""

    object_list: Sequence[Any]
    number: int
    paginator: CountlessPaginator
    has_more: bool

    def has_next(self) -> bool:
        return self.has_more

    def has_previous(self) -> bool:
        return self.number > 1

    def next_page_number(self) -> int:
        if not self.has_next():
            raise ValueError(NO_NEXT_PAGE_MESSAGE)
        return self.number + 1

    def previous_page_number(self) -> int:
        if not self.has_previous():
            raise ValueError(NO_PREVIOUS_PAGE_MESSAGE)
        return self.number - 1

    def start_index(self) -> int:
        if not self.object_list:
            return 0
        return (self.number - 1) * self.paginator.per_page + 1

    def end_index(self) -> int:
        if not self.object_list:
            return 0
        return self.start_index() + len(self.object_list) - 1

    @property
    def known_count(self) -> int:
        return self.end_index() + (1 if self.has_next() else 0)


class CountlessPaginationMixin:
    """Paginate a queryset using LIMIT page-size-plus-one instead of COUNT."""

    def paginate_queryset(self, queryset, page_size):
        raw_page = self.kwargs.get(self.page_kwarg) or self.request.GET.get(
            self.page_kwarg,
            1,
        )
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError) as error:
            raise Http404(NON_NUMERIC_PAGE_MESSAGE) from error
        if page_number < 1:
            raise Http404(NON_POSITIVE_PAGE_MESSAGE)
        if page_number > SEARCH_MAX_PAGE:
            message = f"Search pagination is limited to page {SEARCH_MAX_PAGE}."
            raise SearchPageLimitError(message)

        offset = (page_number - 1) * page_size
        rows = list(queryset[offset : offset + page_size + 1])
        if page_number > 1 and not rows:
            raise Http404(EMPTY_PAGE_MESSAGE)
        has_more = len(rows) > page_size
        object_list = rows[:page_size]
        paginator = CountlessPaginator(per_page=page_size)
        page = CountlessPage(
            object_list=object_list,
            number=page_number,
            paginator=paginator,
            has_more=has_more,
        )
        return paginator, page, object_list, page.has_previous() or page.has_next()


class SearchRequestBudgetMixin:
    """Apply request-complexity and PostgreSQL statement-time boundaries."""

    def dispatch(self, request, *args, **kwargs):
        query = request.GET.get("q", "")
        if len(query) > SEARCH_MAX_QUERY_LENGTH:
            return self._complexity_response(
                f"Search text is limited to {SEARCH_MAX_QUERY_LENGTH} characters.",
            )

        if is_anonymous_public_search(request):
            return self._dispatch_public_index(request, *args, **kwargs)

        return self._dispatch_database_search(request, *args, **kwargs)

    def _dispatch_public_index(self, request, *args, **kwargs):
        try:
            response = super().dispatch(request, *args, **kwargs)
            if hasattr(response, "render"):
                response.render()
        except (FacetSelectionLimitError, SearchPageLimitError) as error:
            return self._complexity_response(str(error))
        except PublicSearchIndexError:
            logger.exception("Public search index is unavailable")
            return self._public_index_unavailable_response()
        return response

    def _dispatch_database_search(self, request, *args, **kwargs):
        try:
            with transaction.atomic(savepoint=False):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET LOCAL statement_timeout = %s",
                        [settings.SEARCH_STATEMENT_TIMEOUT_MS],
                    )
                response = super().dispatch(request, *args, **kwargs)
                if hasattr(response, "render"):
                    response.render()
                return response
        except (FacetSelectionLimitError, SearchPageLimitError) as error:
            return self._complexity_response(str(error))
        except FacetCacheBusyError:
            return self._retry_response("Search facets are currently refreshing.")
        except DatabaseError as error:
            if self._is_statement_timeout(error):
                logger.warning("Interactive search exceeded its database time budget")
                return self._retry_response(
                    "Search is temporarily unavailable because it exceeded "
                    "the time budget.",
                )
            raise

    @staticmethod
    def _is_statement_timeout(error: BaseException) -> bool:
        current: BaseException | None = error
        while current is not None:
            sqlstate = getattr(current, "sqlstate", None) or getattr(
                current,
                "pgcode",
                None,
            )
            if sqlstate == POSTGRES_QUERY_CANCELED:
                return True
            if "statement timeout" in str(current).lower():
                return True
            current = current.__cause__
        return False

    @staticmethod
    def _complexity_response(message: str) -> HttpResponse:
        return HttpResponse(
            f"Too many facet selections or excessive search complexity: {message}",
            status=422,
            content_type="text/plain; charset=utf-8",
        )

    @staticmethod
    def _retry_response(message: str) -> HttpResponse:
        response = HttpResponse(
            message,
            status=503,
            content_type="text/plain; charset=utf-8",
        )
        response.headers["Retry-After"] = str(SEARCH_RETRY_AFTER_SECONDS)
        return response

    @staticmethod
    def _public_index_unavailable_response() -> HttpResponse:
        return public_search_unavailable_response()
