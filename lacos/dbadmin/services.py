import logging
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from lacos.storage.models import BackgroundTask

logger = logging.getLogger(__name__)


class DatabaseStatsService:
    @staticmethod
    def get_pg_stats() -> dict:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_database_size(current_database()),"
                " pg_size_pretty(pg_database_size(current_database())),"
                " version(),"
                " (SELECT count(*) FROM pg_stat_activity"
                "  WHERE datname = current_database()),"
                " (SELECT count(*) FROM information_schema.tables"
                "  WHERE table_schema = 'public'),"
                " (SELECT date_trunc('second', current_timestamp - pg_postmaster_start_time()))"
            )
            row = cursor.fetchone()
        return {
            "db_size": row[0],
            "db_size_pretty": row[1],
            "server_version": row[2],
            "active_connections": row[3],
            "table_count": row[4],
            "uptime": str(row[5]) if row[5] else "N/A",
        }

    @staticmethod
    def get_table_sizes() -> list[dict]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname AS table_name,"
                " reltuples::bigint AS row_estimate,"
                " pg_total_relation_size(c.oid) AS total_size,"
                " pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size_pretty"
                " FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'public' AND c.relkind = 'r'"
                " ORDER BY pg_total_relation_size(c.oid) DESC"
            )
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def get_backup_summary() -> dict:
        backup_names = ["blam_database_backup", "periodic_backup"]
        last_backup = (
            BackgroundTask.objects.filter(task_name__in=backup_names)
            .order_by("-created_at")
            .first()
        )
        total = BackgroundTask.objects.filter(
            task_name__in=backup_names
        ).count()
        successful = BackgroundTask.objects.filter(
            task_name__in=backup_names,
            status=BackgroundTask.Status.SUCCESS,
        ).count()
        return {
            "last_backup": last_backup,
            "last_status": last_backup.status if last_backup else None,
            "last_backup_time": last_backup.created_at if last_backup else None,
            "total_backups": total,
            "successful_backups": successful,
        }

    @staticmethod
    def get_health_warnings() -> list[dict]:
        warnings = []
        backup = DatabaseStatsService.get_backup_summary()
        if backup["last_backup_time"] is None:
            warnings.append({
                "level": "warning",
                "message": "No database backups found.",
            })
        elif backup["last_backup_time"] < timezone.now() - timedelta(hours=24):
            warnings.append({
                "level": "warning",
                "message": f"Last backup was {backup['last_backup_time']:%Y-%m-%d %H:%M}. Consider running a backup.",
            })
        if backup["last_status"] == BackgroundTask.Status.FAILED:
            warnings.append({
                "level": "error",
                "message": "Last backup failed. Check task history for details.",
            })
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT relname, n_dead_tup, n_live_tup"
                    " FROM pg_stat_user_tables"
                    " WHERE n_live_tup > 1000"
                    " AND n_dead_tup::float / GREATEST(n_live_tup, 1) > 0.1"
                    " ORDER BY n_dead_tup DESC LIMIT 5"
                )
                for row in cursor.fetchall():
                    warnings.append({
                        "level": "info",
                        "message": f"Table '{row[0]}' has {row[1]} dead tuples ({row[1]*100//max(row[2],1)}% of live rows). Consider VACUUM.",
                    })
        except Exception as exc:
            logger.warning("Failed to check dead tuples: %s", exc)
        return warnings

    @staticmethod
    def get_periodic_tasks_summary() -> list[dict]:
        from lacos.common.periodic_task_registry import PERIODIC_TASKS

        summary = []
        for task_info in PERIODIC_TASKS:
            last_run = (
                BackgroundTask.objects.filter(task_name=task_info["task_name"])
                .order_by("-created_at")
                .first()
            )
            recent_success = BackgroundTask.objects.filter(
                task_name=task_info["task_name"],
                status=BackgroundTask.Status.SUCCESS,
            ).count()
            recent_failed = BackgroundTask.objects.filter(
                task_name=task_info["task_name"],
                status=BackgroundTask.Status.FAILED,
            ).count()
            summary.append({
                **task_info,
                "last_run": last_run,
                "last_status": last_run.status if last_run else None,
                "last_run_time": last_run.created_at if last_run else None,
                "total_success": recent_success,
                "total_failed": recent_failed,
            })
        return summary
