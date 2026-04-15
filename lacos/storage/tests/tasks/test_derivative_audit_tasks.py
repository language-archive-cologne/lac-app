from unittest.mock import patch

import lacos.storage.derivative_audit_tasks as derivative_audit_tasks
import lacos.storage.tasks as storage_tasks


def test_storage_tasks_imports_derivative_audit_tasks_for_huey_registration():
    assert storage_tasks.audit_derivatives_task is derivative_audit_tasks.audit_derivatives_task
    assert storage_tasks.periodic_derivative_audit is derivative_audit_tasks.periodic_derivative_audit


@patch("lacos.storage.derivative_audit_tasks._run_audit")
def test_periodic_derivative_audit_returns_skipped_when_disabled(mock_run_audit):
    result = derivative_audit_tasks.periodic_derivative_audit()

    assert result == {
        "success": False,
        "skipped": "periodic_derivative_audit_disabled",
        "reason": (
            "Automatic scheduling disabled while S3 throttling is being validated."
        ),
    }
    mock_run_audit.assert_not_called()


@patch("lacos.storage.derivative_audit_tasks.BackgroundTaskService")
@patch("lacos.storage.derivative_audit_tasks._run_audit")
def test_audit_derivatives_task_marks_tracking_failed_when_audit_reports_errors(
    mock_run_audit,
    mock_background_tasks,
):
    mock_run_audit.return_value = {
        "success": False,
        "total_wav_files": 3,
        "errors": 1,
    }

    result = derivative_audit_tasks.audit_derivatives_task.call_local(
        tracking_id="track-1",
    )

    assert result["success"] is False
    mock_background_tasks.mark_running.assert_called_once_with(
        "track-1",
        message="Running derivative audit",
    )
    mock_background_tasks.mark_failed.assert_called_once_with(
        "track-1",
        error_message="Derivative audit completed with 1 errors",
        result=result,
    )
