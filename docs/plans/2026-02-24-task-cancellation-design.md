# Task Cancellation Design

## Problem

Huey worker crashes/restarts leave BackgroundTask records stuck in RUNNING status indefinitely. QUEUED tasks also cannot be cancelled. The UI polls forever on these zombie tasks.

## Solution

Per-task cancel button that revokes queued Huey tasks and marks zombie running tasks as cancelled.

## Changes

### Model: BackgroundTask.Status
- Add `CANCELLED = "cancelled"` choice
- Add `mark_cancelled(message=None)` helper

### Service: BackgroundTaskService
- Add `cancel(task)` method:
  - Guard: only non-terminal states (QUEUED, RUNNING)
  - If QUEUED with huey_task_id: call Huey `revoke()` to prevent execution
  - Set status to CANCELLED

### View: TaskCancelView
- POST `/dbadmin/tasks/<uuid:task_id>/cancel/`
- Returns updated `task_status.html` partial for HTMX swap

### URL
- `path("tasks/<uuid:task_id>/cancel/", TaskCancelView.as_view(), name="task_cancel")`

### Template: task_status.html
- Cancel button on QUEUED/RUNNING tasks
- `hx-post` to cancel endpoint, `hx-swap="outerHTML"`
- Cancelled tasks show warning badge, stop polling
