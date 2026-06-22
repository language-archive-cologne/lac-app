import pytest

from lacos.dbadmin.postgres_observability import (
    PgStatStatementsService,
    _is_pg_stat_statements_preloaded,
)
from lacos.dbadmin.services import DatabaseStatsService


@pytest.mark.django_db
class TestDatabaseStatsService:
    def test_get_pg_stats_returns_expected_keys(self):
        stats = DatabaseStatsService.get_pg_stats()
        assert "db_size" in stats
        assert "db_size_pretty" in stats
        assert "table_count" in stats
        assert "active_connections" in stats
        assert "server_version" in stats
        assert "uptime" in stats

    def test_get_pg_stats_db_size_is_positive(self):
        stats = DatabaseStatsService.get_pg_stats()
        assert stats["db_size"] > 0

    def test_get_table_sizes_returns_list(self):
        tables = DatabaseStatsService.get_table_sizes()
        assert isinstance(tables, list)
        assert len(tables) > 0

    def test_get_table_sizes_entry_has_expected_keys(self):
        tables = DatabaseStatsService.get_table_sizes()
        entry = tables[0]
        assert "table_name" in entry
        assert "row_estimate" in entry
        assert "total_size" in entry
        assert "total_size_pretty" in entry

    def test_get_backup_summary_returns_dict(self):
        summary = DatabaseStatsService.get_backup_summary()
        assert isinstance(summary, dict)
        assert "last_backup" in summary
        assert "last_status" in summary
        assert "total_backups" in summary

    def test_get_health_warnings_returns_list(self):
        warnings = DatabaseStatsService.get_health_warnings()
        assert isinstance(warnings, list)

    def test_get_pg_stat_statements_summary_returns_expected_keys(self):
        summary = PgStatStatementsService.get_summary()

        assert "available" in summary
        assert "preloaded" in summary
        assert "extension_installed" in summary
        assert "top_queries" in summary
        assert "error" in summary


def test_pg_stat_statements_preload_detection_allows_multiple_libraries():
    assert _is_pg_stat_statements_preloaded("pg_cron, pg_stat_statements")


def test_pg_stat_statements_preload_detection_rejects_missing_library():
    assert not _is_pg_stat_statements_preloaded("pg_cron")
