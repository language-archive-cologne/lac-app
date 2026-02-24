# Task Cancellation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-task cancel buttons so admins can cancel queued tasks (revoking them in Huey) and mark zombie running tasks as cancelled.

**Architecture:** Add CANCELLED status to BackgroundTask model, a cancel service method that revokes queued Huey tasks and marks the DB record, a new HTMX endpoint, and a cancel button in the task status partial.

**Tech Stack:** Django, Huey (djhuey), HTMX, DaisyUI

---

### Task 1: Add CANCELLED status and mark_cancelled to BackgroundTask model

**Files:**
- Modify: `lacos/storage/models/background_task.py:7-11` (Status choices)
- Modify: `lacos/storage/models/background_task.py:39-44` (add method after mark_failed)
- Test: `lacos/dbadmin/tests/test_task_views.py`

**Step 1: Write the failing test**

In `lacos/dbadmin/tests/test_task_views.py`, add:

```python
@pytest.mark.django_db
def test_background_task_mark_cancelled():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.RUNNING,
        message="Processing...",
    )
    task.mark_cancelled("Cancelled by admin")
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.CANCELLED
    assert task.message == "Cancelled by admin"
```

**Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py::test_background_task_mark_cancelled -v`
Expected: FAIL — `AttributeError: type object 'Status' has no attribute 'CANCELLED'`

**Step 3: Write minimal implementation**

In `lacos/storage/models/background_task.py`:

Add to `Status` choices (after line 11):
```python
CANCELLED = "cancelled", "Cancelled"
```

Add method after `mark_failed` (after line 44):
```python
def mark_cancelled(self, message: str | None = None):
    self.status = self.Status.CANCELLED
    if message is not None:
        self.message = message
    self.save(update_fields=["status", "message", "updated_at"])
```

**Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py::test_background_task_mark_cancelled -v`
Expected: PASS

**Step 5: Commit**

```
git add lacos/storage/models/background_task.py lacos/dbadmin/tests/test_task_views.py
git commit -m "feat(dbadmin): add CANCELLED status to BackgroundTask model"
```

---

### Task 2: Add cancel method to BackgroundTaskService

**Files:**
- Modify: `lacos/storage/services/background_task_service.py:64` (add after mark_failed)
- Test: `lacos/dbadmin/tests/test_task_views.py`

**Step 1: Write the failing tests**

In `lacos/dbadmin/tests/test_task_views.py`, add:

```python
@pytest.mark.django_db
def test_cancel_queued_task_revokes_huey_and_marks_cancelled():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.QUEUED,
        huey_task_id="huey-abc",
    )
    with patch("lacos.storage.services.background_task_service.revoke_by_id") as mock_revoke:
        BackgroundTaskService.cancel(task)
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.CANCELLED
    assert "Cancelled" in task.message
    mock_revoke.assert_called_once_with("huey-abc")


@pytest.mark.django_db
def test_cancel_running_task_marks_cancelled_without_huey_revoke():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.RUNNING,
        huey_task_id="huey-def",
    )
    with patch("lacos.storage.services.background_task_service.revoke_by_id") as mock_revoke:
        BackgroundTaskService.cancel(task)
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.CANCELLED
    mock_revoke.assert_not_called()


@pytest.mark.django_db
def test_cancel_completed_task_raises_value_error():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.SUCCESS,
    )
    with pytest.raises(ValueError, match="Cannot cancel"):
        BackgroundTaskService.cancel(task)
```

**Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py -k "test_cancel" -v`
Expected: FAIL — `AttributeError: type object 'BackgroundTaskService' has no attribute 'cancel'`

**Step 3: Write minimal implementation**

In `lacos/storage/services/background_task_service.py`:

Add import at top (after line 4):
```python
from huey.contrib.djhuey import revoke_by_id
```

Add method after `mark_failed` (after line 64):
```python
@staticmethod
def cancel(task_id: str | BackgroundTask) -> None:
    task = BackgroundTaskService._get_task_or_none(task_id)
    if not task:
        return
    terminal = {BackgroundTask.Status.SUCCESS, BackgroundTask.Status.FAILED, BackgroundTask.Status.CANCELLED}
    if task.status in terminal:
        raise ValueError(f"Cannot cancel task in {task.status} status")
    if task.status == BackgroundTask.Status.QUEUED and task.huey_task_id:
        revoke_by_id(task.huey_task_id)
    task.mark_cancelled("Cancelled by admin")
    logger.info("Cancelled background task %s (%s)", task.id, task.task_name)
```

Note: `revoke_by_id` is available from `huey.contrib.djhuey` — it revokes a task by its Huey ID string. This only prevents execution of QUEUED tasks; it has no effect on already-running tasks.

**Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py -k "test_cancel" -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```
git add lacos/storage/services/background_task_service.py lacos/dbadmin/tests/test_task_views.py
git commit -m "feat(dbadmin): add cancel method to BackgroundTaskService"
```

---

### Task 3: Add TaskCancelView and URL

**Files:**
- Modify: `lacos/dbadmin/views.py:174` (add view before TaskStatusView)
- Modify: `lacos/dbadmin/urls.py:12` (add URL after task_status)
- Test: `lacos/dbadmin/tests/test_task_views.py`

**Step 1: Write the failing tests**

In `lacos/dbadmin/tests/test_task_views.py`, add:

```python
@pytest.mark.django_db
def test_task_cancel_view_cancels_queued_task(superuser_client):
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.QUEUED,
    )
    with patch("lacos.dbadmin.views.BackgroundTaskService.cancel"):
        response = superuser_client.post(
            reverse("dbadmin:task_cancel", kwargs={"task_id": task.id}),
            HTTP_HX_REQUEST="true",
        )
    assert response.status_code == 200
    assert f"dbadmin-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
def test_task_cancel_view_returns_error_for_completed_task(superuser_client):
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.SUCCESS,
    )
    response = superuser_client.post(
        reverse("dbadmin:task_cancel", kwargs={"task_id": task.id}),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_task_cancel_view_requires_superuser(non_superuser_client):
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.QUEUED,
    )
    response = non_superuser_client.post(
        reverse("dbadmin:task_cancel", kwargs={"task_id": task.id}),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
```

**Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py -k "test_task_cancel_view" -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'task_cancel' not found`

**Step 3: Write minimal implementation**

In `lacos/dbadmin/views.py`, add after `TaskEnqueueView` class (before `TaskStatusView`):

```python
class TaskCancelView(SuperuserRequiredMixin, View):
    def post(self, request, task_id, *args, **kwargs):
        task = get_object_or_404(BackgroundTask, pk=task_id)
        try:
            BackgroundTaskService.cancel(task)
        except ValueError as exc:
            return HttpResponse(str(exc), status=400)
        task.refresh_from_db()
        return HttpResponse(
            render_to_string(
                "dbadmin/partials/task_status.html",
                {"task": task},
                request=request,
            )
        )
```

In `lacos/dbadmin/urls.py`, add after the task_status line (line 11):

```python
path("tasks/<uuid:task_id>/cancel/", views.TaskCancelView.as_view(), name="task_cancel"),
```

**Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py -k "test_task_cancel_view" -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```
git add lacos/dbadmin/views.py lacos/dbadmin/urls.py lacos/dbadmin/tests/test_task_views.py
git commit -m "feat(dbadmin): add task cancel endpoint"
```

---

### Task 4: Add cancel button to task_status.html partial

**Files:**
- Modify: `lacos/dbadmin/templates/dbadmin/partials/task_status.html`

**Step 1: Update the partial**

Replace the entire `task_status.html` with this updated version that:
- Adds a cancel button for QUEUED/RUNNING tasks (next to the status badge)
- Shows CANCELLED state with `alert-warning` styling
- Stops HTMX polling for CANCELLED tasks (same as SUCCESS/FAILED)

```html
{% load humanize %}
{% with status=task.status %}
<div id="dbadmin-task-{{ task.id }}"
     class="alert {% if status == 'failed' %}alert-error{% elif status == 'success' %}alert-success{% elif status == 'cancelled' %}alert-warning{% else %}alert-info{% endif %}"
     {% if status != 'success' and status != 'failed' and status != 'cancelled' %}
        hx-get="{% url 'dbadmin:task_status' task.id %}"
        hx-trigger="load, every 4s"
        hx-target="this"
        hx-swap="outerHTML"
     {% endif %}>
    <div class="flex w-full items-start justify-between gap-3">
        <div>
            <div class="font-semibold text-sm">{{ task.description|default:task.task_name }}</div>
            <div class="text-xs opacity-80 mt-1">
                {% if task.message %}{{ task.message }}{% else %}Task {{ task.status }}.{% endif %}
            </div>
            <div class="text-[11px] opacity-70 mt-1">
                Started {{ task.created_at|naturaltime }}
                {% if task.metadata.task_id %} · Huey <code>{{ task.metadata.task_id }}</code>{% endif %}
            </div>
            {% if status == 'success' and task.result %}
            <div class="text-[11px] opacity-80 mt-2">
                {% if task.result.collections_reindexed %}
                    Collections: {{ task.result.collections_reindexed }} · Bundles: {{ task.result.bundles_reindexed }}
                {% elif task.result.backup_file %}
                    {{ task.result.backup_file }} to <code>s3://{{ task.result.bucket }}/{{ task.result.key }}</code>
                {% endif %}
            </div>
            {% elif status == 'failed' and task.error %}
            <div class="text-[11px] mt-2 break-words">{{ task.error }}</div>
            {% endif %}
        </div>
        <div class="flex items-center gap-2">
            {% if status == 'queued' or status == 'running' %}
            <button
                hx-post="{% url 'dbadmin:task_cancel' task.id %}"
                hx-target="#dbadmin-task-{{ task.id }}"
                hx-swap="outerHTML"
                class="btn btn-ghost btn-xs"
                title="Cancel task">
                ✕
            </button>
            {% endif %}
            <span class="badge badge-outline badge-sm">{{ status }}</span>
        </div>
    </div>
</div>
{% endwith %}
```

**Step 2: Run full test suite to verify nothing broke**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/test_task_views.py -v`
Expected: All tests PASS

**Step 3: Commit**

```
git add lacos/dbadmin/templates/dbadmin/partials/task_status.html
git commit -m "feat(dbadmin): add cancel button to task status partial"
```

---

### Task 5: Generate migration for new status choice

**Step 1: Generate migration**

Run: `docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations storage --name add_cancelled_status`

**Step 2: Verify migration was created**

Check: `ls lacos/storage/migrations/ | grep cancelled`
Expected: A new migration file

**Step 3: Run migration**

Run: `docker compose -f docker-compose.local.yml run --rm django python manage.py migrate`
Expected: Migration applied successfully

**Step 4: Run full test suite**

Run: `docker compose -f docker-compose.local.yml run --rm django pytest lacos/dbadmin/tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```
git add lacos/storage/migrations/
git commit -m "feat(dbadmin): add migration for cancelled task status"
```

---

### Task 6: Rebuild Tailwind CSS

The cancel button uses `btn-ghost` and `btn-xs` classes. Make sure they're in the compiled CSS.

**Step 1: Rebuild CSS**

Run: `cd theme/static_src && npx @tailwindcss/cli -i css/input.css -o ../static/css/output.css`

**Step 2: Verify cancel-related classes exist**

Check that `btn-ghost` is in the output CSS (it likely already is from other templates).

**Step 3: No commit needed** (output.css is gitignored)
