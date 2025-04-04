from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
import logging

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle

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
        elif model_type.lower() == 'bundle':
            model = get_object_or_404(Bundle, pk=object_id)
            model_name = "Bundle"
        else:
            return HttpResponseBadRequest(f"Invalid model type: {model_type}")
        
        logger.info(f"Deleting {model_name} with ID: {object_id}")
        model.delete()
        logger.info(f"{model_name} with ID: {object_id} successfully deleted")
        
        return HttpResponse("", status=200)
        
    except Exception as e:
        logger.error(f"Error deleting {model_type} with ID {object_id}: {str(e)}")
        return HttpResponseBadRequest(f"Error deleting {model_type}: {str(e)}")
