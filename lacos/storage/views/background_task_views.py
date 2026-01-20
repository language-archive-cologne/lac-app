import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from lacos.storage.models import BackgroundTask
from lacos.storage.permissions import archivist_required


@archivist_required
@require_GET
def background_task_status(request, task_id):
    task = get_object_or_404(BackgroundTask, pk=task_id)
    response = render(request, 'storage/background_task_status.html', {'task': task})

    if task.status == BackgroundTask.Status.SUCCESS:
        message = task.message or 'Task completed successfully.'
        response['HX-Trigger'] = json.dumps({'showMessage': {'message': message, 'level': 'success'}})
    elif task.status == BackgroundTask.Status.FAILED:
        message = task.error or 'Background task failed.'
        response['HX-Trigger'] = json.dumps({'showMessage': {'message': message, 'level': 'error'}})

    return response
