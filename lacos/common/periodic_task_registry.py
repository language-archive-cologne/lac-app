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
        "task_name": "periodic_derivative_audit",
        "label": "Derivative Audit",
        "schedule": "0 3 * * *",
        "schedule_human": "Daily at 3:00 AM UTC",
        "disabled": True,
        "disabled_reason": "Automatic scheduling disabled while S3 throttling is being validated.",
    },
]
