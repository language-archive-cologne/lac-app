import logging

from django.db import connection

logger = logging.getLogger(__name__)

PG_STAT_STATEMENTS_EXTENSION = "pg_stat_statements"


class PgStatStatementsService:
    @staticmethod
    def get_summary(limit: int = 10) -> dict:
        if connection.vendor != "postgresql":
            return _empty_summary(error="Query statistics require PostgreSQL.")

        try:
            preloaded_libraries = _get_preloaded_libraries()
            extension_installed = _is_extension_installed()
            preloaded = _is_pg_stat_statements_preloaded(preloaded_libraries)
            summary = {
                "available": preloaded and extension_installed,
                "preloaded": preloaded,
                "extension_installed": extension_installed,
                "top_queries": [],
                "error": "",
            }
            if not summary["available"]:
                return summary
            summary["top_queries"] = _get_top_queries(limit)
            return summary
        except Exception as exc:
            logger.warning("Failed to load pg_stat_statements summary: %s", exc)
            return _empty_summary(error=str(exc))


def _get_preloaded_libraries() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('shared_preload_libraries', true)")
        row = cursor.fetchone()
    return row[0] or ""


def _is_extension_installed() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS("
            " SELECT 1 FROM pg_extension WHERE extname = %s"
            ")",
            [PG_STAT_STATEMENTS_EXTENSION],
        )
        row = cursor.fetchone()
    return bool(row[0])


def _get_top_queries(limit: int) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT calls,"
            " round(total_exec_time::numeric, 1) AS total_exec_time_ms,"
            " round(mean_exec_time::numeric, 2) AS mean_exec_time_ms,"
            " rows,"
            " left(regexp_replace(query, '\\s+', ' ', 'g'), 180) AS query"
            " FROM pg_stat_statements"
            " WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())"
            " AND query NOT ILIKE %s"
            " ORDER BY total_exec_time DESC"
            " LIMIT %s",
            ["%pg_stat_statements%", limit],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _is_pg_stat_statements_preloaded(preloaded_libraries: str) -> bool:
    libraries = {
        library.strip()
        for library in preloaded_libraries.split(",")
        if library.strip()
    }
    return PG_STAT_STATEMENTS_EXTENSION in libraries


def _empty_summary(error: str = "") -> dict:
    return {
        "available": False,
        "preloaded": False,
        "extension_installed": False,
        "top_queries": [],
        "error": error,
    }
