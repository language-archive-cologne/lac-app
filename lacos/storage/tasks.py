import logging
from typing import Dict, Any
from huey.contrib.djhuey import db_task, task
try:
    from lacos.config.huey import HUEY as huey
except ImportError:
    from huey.contrib.djhuey import HUEY as huey

from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.ocfl_service import OCFLService
from lacos.storage.services.ocfl_fixture_manager import OCFLFixtureManager

logger = logging.getLogger(__name__)


@task()
def convert_folder_to_ocfl_task(bucket_name: str, folder_path: str, create_backup: bool = True, force: bool = False) -> Dict[str, Any]:
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
        bucket_service = BucketService()
        ocfl_service = OCFLService(bucket_service)
        fixture_manager = OCFLFixtureManager(ocfl_service)

        # Analyze the folder structure first
        logger.info(f"Analyzing folder structure: {bucket_name}/{folder_path}")
        analysis = fixture_manager.analyze_single_folder(
            bucket_name=bucket_name,
            folder_path=folder_path
        )

        if not analysis:
            error_msg = 'Failed to analyze folder structure'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }

        # Check for risks
        risks = []
        if analysis.get('has_metadata'):
            risks.append('Folder contains existing metadata files')
        if analysis.get('nested_depth', 0) > 3:
            risks.append(f"Deep nesting detected: {analysis.get('nested_depth')} levels")

        # If there are risks and no force flag, return error
        if risks and not force:
            error_msg = f"Conversion risks detected: {', '.join(risks)}. Use force=True to proceed anyway."
            logger.warning(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'risks': risks,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }

        # Create backup if requested
        backup_location = None
        if create_backup:
            logger.info(f"Creating backup for {bucket_name}/{folder_path}")
            backup_result = fixture_manager.create_backup(
                bucket_name=bucket_name,
                folder_path=folder_path
            )
            if backup_result.get('success'):
                backup_location = backup_result.get('backup_path')
                logger.info(f"Backup created at: {backup_location}")
            else:
                logger.warning("Failed to create backup, continuing anyway")

        # Perform the conversion
        logger.info(f"Performing OCFL conversion for {bucket_name}/{folder_path}")
        conversion_result = fixture_manager.convert_single_folder(
            bucket_name=bucket_name,
            folder_path=folder_path,
            dry_run=False
        )

        if conversion_result.get('success'):
            logger.info(f"OCFL conversion completed successfully for {bucket_name}/{folder_path}")
            return {
                'success': True,
                'message': f'Successfully converted {folder_path} to OCFL format',
                'backup_location': backup_location,
                'bucket_name': bucket_name,
                'folder_path': folder_path,
                'analysis': analysis,
                'conversion_details': conversion_result
            }
        else:
            error_msg = conversion_result.get('error', 'Unknown error occurred during conversion')
            logger.error(f"OCFL conversion failed for {bucket_name}/{folder_path}: {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'bucket_name': bucket_name,
                'folder_path': folder_path,
                'analysis': analysis
            }

    except Exception as e:
        error_msg = f"Error during OCFL conversion: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            'success': False,
            'error': error_msg,
            'bucket_name': bucket_name,
            'folder_path': folder_path
        }


@task()
def analyze_folder_for_ocfl_task(bucket_name: str, folder_path: str) -> Dict[str, Any]:
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
        bucket_service = BucketService()
        ocfl_service = OCFLService(bucket_service)
        fixture_manager = OCFLFixtureManager(ocfl_service)

        # Analyze the folder structure
        analysis = fixture_manager.analyze_single_folder(
            bucket_name=bucket_name,
            folder_path=folder_path
        )

        if analysis:
            logger.info(f"Folder analysis completed for {bucket_name}/{folder_path}")
            return {
                'success': True,
                'analysis': analysis,
                'bucket_name': bucket_name,
                'folder_path': folder_path
            }
        else:
            error_msg = 'Failed to analyze folder structure'
            logger.error(error_msg)
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