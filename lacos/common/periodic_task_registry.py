"""Registry of known periodic tasks for dashboard display."""

from __future__ import annotations

PERIODIC_TASKS = [
    {
        "task_name": "periodic_backup",
        "label": "Database Backup",
        "schedule": "0 2 * * *",
        "schedule_human": "Daily at 2:00 AM UTC",
    },
    {
        "task_name": "periodic_upload_verification",
        "label": "Upload Verification",
        "schedule": "*/15 * * * *",
        "schedule_human": "Every 15 minutes",
    },
    {
        "task_name": "periodic_saml_metadata",
        "label": "SAML Metadata Refresh",
        "schedule": "5 3 * * *",
        "schedule_human": "Daily at 3:05 AM UTC",
    },
    {
        "task_name": "periodic_media_audit",
        "label": "Media Audit (all collections)",
        "schedule": "30 3 * * 0",
        "schedule_human": "Sundays at 3:30 AM UTC",
    },
    {
        "task_name": "periodic_media_derivative_check",
        "label": "Media Derivative Check",
        "schedule": "30 4 * * *",
        "schedule_human": "Daily at 4:30 AM UTC",
    },
]
