import json
import logging
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import render

from lacos.storage.tasks import convert_folder_to_ocfl_task, analyze_folder_for_ocfl_task

logger = logging.getLogger(__name__)


class ConvertToOCFLView(View):
    """Handle OCFL conversion requests via HTMX"""

    def post(self, request, bucket_name, folder_path):
        """Convert a folder to OCFL format using background task"""
        try:
            # Check if backup is requested
            create_backup = request.POST.get('create_backup', 'false').lower() == 'true'
            force = request.POST.get('force', 'false').lower() == 'true'

            logger.info(f"Triggering OCFL conversion task for {bucket_name}/{folder_path}")

            # Trigger the background task
            task_result = convert_folder_to_ocfl_task(
                bucket_name=bucket_name,
                folder_path=folder_path,
                create_backup=create_backup,
                force=force
            )

            # Get task ID for tracking
            task_id = task_result.id if hasattr(task_result, 'id') else 'unknown'

            # Return immediate success response with task tracking
            return HttpResponse(
                f"""
                <div class="alert alert-info">
                    <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div>
                        <span class="font-semibold">OCFL conversion started!</span>
                        <div class="text-sm mt-1">
                            Converting: {folder_path}
                            <br>Task ID: {task_id}
                            <br>This may take several minutes. You'll be notified when complete.
                        </div>
                        <div class="mt-2">
                            <div class="loading loading-spinner loading-sm inline-block mr-2"></div>
                            <span class="text-sm">Processing in background...</span>
                        </div>
                    </div>
                </div>
                """,
                headers={
                    'HX-Trigger': json.dumps({
                        'showMessage': {
                            'message': f'OCFL conversion started for {folder_path}. Task ID: {task_id}',
                            'level': 'info'
                        }
                    })
                }
            )

        except Exception as e:
            logger.error(f"Error triggering OCFL conversion task: {str(e)}")
            return HttpResponse(
                f"""
                <div class="alert alert-error">
                    <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>Error starting conversion: {str(e)}</span>
                </div>
                """
            )


def ocfl_conversion_modal(request, bucket_name, folder_path):
    """Render the OCFL conversion modal content"""
    return render(request, 'storage/ocfl_conversion_modal.html', {
        'bucket_name': bucket_name,
        'folder_path': folder_path
    })