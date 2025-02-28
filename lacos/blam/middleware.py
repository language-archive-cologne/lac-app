# middleware.py
from django.db.models import signals
from threading import local
_thread_locals = local()

def get_current_user():
    """Returns the current user, if available, otherwise None."""
    return getattr(_thread_locals, 'user', None)

class AuditMiddleware:
    """
    Middleware that stores the current user in thread locals and automatically sets
    created_by and updated_by fields in BaseModel instances.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # Connect to Django's signal system
        signals.pre_save.connect(self.pre_save_handler)

    def __call__(self, request):
        # Store the user in thread locals if authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            _thread_locals.user = request.user
        else:
            _thread_locals.user = None

        response = self.get_response(request)

        # Clear thread locals at the end of the request
        _thread_locals.user = None

        return response

    def pre_save_handler(self, sender, instance, **kwargs):
        """
        Signal handler that sets created_by and updated_by fields.
        Only applies to models that inherit from BaseModel (directly or through abstract classes).
        """
        # Import here to avoid circular imports
        from lacos.blam.models.base_model import BaseModel

        # Check if this instance inherits from BaseModel
        if not isinstance(instance, BaseModel):
            return

        # Get current user from thread locals
        user = get_current_user()
        if user:
            # If this is a new instance (being created)
            if instance.pk is None and not getattr(instance, 'created_by', None):
                instance.created_by = user
            # Always update the updated_by field
            instance.updated_by = user