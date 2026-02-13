from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db import transaction
import json
import logging

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.permissions import can_manage_bundle, can_manage_collection

logger = logging.getLogger(__name__)

@require_POST
def delete_blam_model(request, model_type, object_id):
    """
    Deletes a BLAM model (Collection or Bundle) when requested through the UI.
    This will properly trigger all cascade delete operations through the model's
    delete method and associated signal handlers.
    
    Args:
        request: The HTTP request object
        model_type: The type of model to delete ('collection' or 'bundle')
        object_id: The primary key of the object to delete
        
    Returns:
        HTTP 200 response if successful, appropriate error response otherwise
    """
    try:
        if model_type.lower() == 'collection':
            model = get_object_or_404(Collection, pk=object_id)
            model_name = "Collection"
            if not can_manage_collection(request.user, model):
                raise PermissionDenied("Collection manager access required.")
        elif model_type.lower() == 'bundle':
            model = get_object_or_404(Bundle, pk=object_id)
            model_name = "Bundle"
            if not can_manage_bundle(request.user, model):
                raise PermissionDenied("Collection manager access required.")
        else:
            return HttpResponseBadRequest(f"Invalid model type: {model_type}")
        
        logger.info(f"Deleting {model_name} with ID: {object_id}")

        if model_type.lower() == 'collection':
            bundles = Bundle.objects.filter(structural_info__is_member_of_collection=model).distinct()
            logger.info(f"Deleting {bundles.count()} bundle(s) linked to Collection ID: {object_id}")
            with transaction.atomic():
                for bundle in bundles:
                    bundle.delete()
                model.delete()
        else:
            model.delete()

        logger.info(f"{model_name} with ID: {object_id} successfully deleted")

        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps({"blam-metadata-refresh": True})
        return response
        
    except Exception as e:
        logger.error(f"Error deleting {model_type} with ID {object_id}: {str(e)}")
        return HttpResponseBadRequest(f"Error deleting {model_type}: {str(e)}")
