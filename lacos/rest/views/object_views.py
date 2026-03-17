from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
import logging

from lacos.rest.legacy_upload_access import build_legacy_upload_denied_response
from lacos.storage.services.upload_service import UploadService

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def copy_object(request):
    """
    Copy an object from one location to another within S3.
    
    Request should include:
    - source_key: Source object key (path)
    - dest_key: Destination object key (path)
    - source_bucket: (optional) Source bucket name
    - dest_bucket: (optional) Destination bucket name
    
    Returns:
        A Response object with copy operation information and status code
    """
    data = request.data
    
    # Extract and validate parameters
    source_key = data.get('source_key')
    dest_key = data.get('dest_key')
    source_bucket = data.get('source_bucket')
    dest_bucket = data.get('dest_bucket')
    
    # Validate required parameters
    if not source_key or not dest_key:
        logger.warning("Missing required parameters for copying object")
        return Response(
            {"success": False, "error": "Missing required parameters: source_key and dest_key are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    denied_response = build_legacy_upload_denied_response(
        request.user,
        s3_keys=[source_key, dest_key],
    )
    if denied_response is not None:
        return denied_response
    
    # Call service layer
    service = UploadService()
    result = service.copy_object(
        source_key=source_key,
        dest_key=dest_key,
        source_bucket=source_bucket,
        dest_bucket=dest_bucket
    )
    
    # Handle service result and return appropriate HTTP response
    if result.get('success') is False:
        logger.error("Failed to copy object", extra={"source_key": source_key, "dest_key": dest_key, "error": result.get('error')})
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    logger.info("Successfully copied object", extra={"source_key": source_key, "dest_key": dest_key})
    return Response(result) 
