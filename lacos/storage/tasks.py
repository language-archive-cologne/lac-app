import logging
from typing import Dict, Any
from huey.contrib.djhuey import db_task, task
try:
    from lacos.config.huey import HUEY as huey
except ImportError:
    from huey.contrib.djhuey import HUEY as huey

from lacos.storage.services.registry import get_bucket_service
from lacos.storage.services.ocfl_service import OCFLService
from lacos.storage.services.ocfl_fixture_manager import OCFLFixtureManager
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


@task()
def convert_folder_to_ocfl_task(
    bucket_name: str,
    folder_path: str,
    create_backup: bool = True,
    force: bool = False,
    tracking_id: str | None = None,
) -> Dict[str, Any]:
    """
    Convert a folder to OCFL format in a background task.

    Args:
        bucket_name: Name of the bucket containing the folder
        folder_path: Path to the folder to convert
        create_backup: Whether to create a backup before conversion
        force: Force conversion even if risks are detected

    Returns:
        Dict with conversion results
    """
    logger.info(f"Starting OCFL conversion task for {bucket_name}/{folder_path}")

    try:
        # Initialize services
        bucket_service = get_bucket_service()
        ocfl_service = OCFLService(bucket_service)
        fixture_manager = OCFLFixtureManager(bucket_service)

        if tracking_id:
            BackgroundTaskService.mark_running(tracking_id, message="Analyzing folder structure")

        # Analyze the folder structure first
        logger.info(f"Analyzing folder structure: {bucket_name}/{folder_path}")
        analysis_result = ocfl_service.analyze_folder_structure(bucket_name, folder_path)

        if not analysis_result.get('success'):
            error_msg = analysis_result.get('error', 'Failed to analyze folder structure')
            logger.error(error_msg)
            if tracking_id:
                BackgroundTaskService.mark_failed(tracking_id, error_message=error_msg)
            return {
                'success': False,
                'error': error_msg,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }

        structure = analysis_result.get('structure_analysis', {}) or {}

        # Check for risks
        risks = []
        if structure.get('has_metadata_files'):
            risks.append('Folder contains existing metadata files')
        if structure.get('has_ocfl_marker') and not structure.get('is_ocfl_compliant'):
            risks.append('Folder already contains partial OCFL markers')

        # If there are risks and no force flag, return error
        if risks and not force:
            error_msg = f"Conversion risks detected: {', '.join(risks)}. Use force=True to proceed anyway."
            logger.warning(error_msg)
            if tracking_id:
                BackgroundTaskService.mark_failed(tracking_id, error_message=error_msg, result={'analysis': analysis_result})
            return {
                'success': False,
                'error': error_msg,
                'risks': risks,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }

        # Create backup if requested
        backup_location = None
        backup_id = None
        if create_backup:
            logger.info(f"Creating backup for {bucket_name}/{folder_path}")
            try:
                backup_id = fixture_manager.create_fixture_backup(
                    bucket_name=bucket_name,
                    folder_path=folder_path
                )
                backup_record = fixture_manager.active_backups.get(backup_id)
                if backup_record:
                    backup_location = backup_record.backup_location
                    logger.info(f"Backup created: {backup_id} at {backup_location}")
                    if tracking_id:
                        BackgroundTaskService.touch(tracking_id, message="Backup created")
            except Exception as backup_error:
                logger.warning(f"Failed to create backup: {backup_error}. Continuing without backup.")
                if tracking_id:
                    BackgroundTaskService.touch(tracking_id, message=f"Backup failed: {backup_error}")

        # Perform the conversion
        logger.info(f"Performing OCFL conversion for {bucket_name}/{folder_path}")
        if tracking_id:
            BackgroundTaskService.touch(tracking_id, message="Executing conversion")
        conversion_result = ocfl_service.convert_bundle_to_ocfl(bucket_name, folder_path)

        if conversion_result.get('success'):
            logger.info(f"OCFL conversion completed successfully for {bucket_name}/{folder_path}")
            payload = {
                'success': True,
                'message': f'Successfully converted {folder_path} to OCFL format',
                'backup_location': backup_location,
                'backup_id': backup_id,
                'bucket_name': bucket_name,
                'folder_path': folder_path,
                'analysis': analysis_result,
                'conversion_details': conversion_result
            }

            if tracking_id:
                BackgroundTaskService.mark_success(
                    tracking_id,
                    message="Conversion completed",
                    result={
                        'bucket_name': bucket_name,
                        'folder_path': folder_path,
                        'conversion': conversion_result,
                        'structure': structure,
                        'backup_id': backup_id,
                    },
                )

            return payload

        error_msg = conversion_result.get('error', 'Unknown error occurred during conversion')
        logger.error(f"OCFL conversion failed for {bucket_name}/{folder_path}: {error_msg}")
        if tracking_id:
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=error_msg,
                result={
                    'bucket_name': bucket_name,
                    'folder_path': folder_path,
                    'structure': structure,
                },
            )
        return {
            'success': False,
            'error': error_msg,
            'bucket_name': bucket_name,
            'folder_path': folder_path,
            'analysis': analysis_result
        }

    except Exception as e:
        error_msg = f"Error during OCFL conversion: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if tracking_id:
            BackgroundTaskService.mark_failed(tracking_id, error_message=error_msg)
        return {
            'success': False,
            'error': error_msg,
            'bucket_name': bucket_name,
            'folder_path': folder_path
        }


@task()
def analyze_folder_for_ocfl_task(bucket_name: str, folder_path: str, tracking_id: str | None = None) -> Dict[str, Any]:
    """
    Analyze a folder to check if it's suitable for OCFL conversion.

    Args:
        bucket_name: Name of the bucket containing the folder
        folder_path: Path to the folder to analyze

    Returns:
        Dict with analysis results
    """
    logger.info(f"Analyzing folder for OCFL suitability: {bucket_name}/{folder_path}")

    try:
        # Initialize services
        bucket_service = get_bucket_service()
        ocfl_service = OCFLService(bucket_service)

        if tracking_id:
            BackgroundTaskService.mark_running(tracking_id, message="Analyzing folder")

        analysis_result = ocfl_service.analyze_folder_structure(bucket_name, folder_path)

        if analysis_result.get('success'):
            logger.info(f"Folder analysis completed for {bucket_name}/{folder_path}")
            if tracking_id:
                BackgroundTaskService.mark_success(
                    tracking_id,
                    message="Analysis complete",
                    result={'bucket_name': bucket_name, 'folder_path': folder_path, 'structure': analysis_result.get('structure_analysis')},
                )
            return {
                'success': True,
                'analysis': analysis_result,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }
        else:
            error_msg = analysis_result.get('error', 'Failed to analyze folder structure')
            logger.error(error_msg)
            if tracking_id:
                BackgroundTaskService.mark_failed(
                    tracking_id,
                    error_message=error_msg,
                    result={'bucket_name': bucket_name, 'folder_path': folder_path},
                )
            return {
                'success': False,
                'error': error_msg,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }

    except Exception as e:
        error_msg = f"Error during folder analysis: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            'success': False,
            'error': error_msg,
            'bucket_name': bucket_name,
            'folder_path': folder_path
        }
