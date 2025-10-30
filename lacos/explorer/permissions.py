from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.utils.translation import gettext_lazy as _

from lacos.storage.services.acl_evaluation_service import ACLEvaluationService, ACLCheckResult


class ACLPermissionMixin:
    """
    Mixin that evaluates ACL permissions before dispatching a class-based view.

    Subclasses must either inherit from a class providing ``get_object`` (e.g.
    ``DetailView``) or override :meth:`get_acl_object`.
    """

    required_acl_mode: str = "acl:Read"
    permission_denied_message: str = _("You do not have permission to access this resource.")

    _acl_cached_object: Optional[Any] = None
    acl_result: Optional[ACLCheckResult] = None

    def dispatch(self, request, *args, **kwargs):
        acl_object = self.get_acl_object(request, *args, **kwargs)
        if acl_object is None:
            raise PermissionDenied(_("Unable to determine the object to authorise."))

        service = self.get_acl_service()
        result = service.evaluate(request.user, acl_object, mode=self.required_acl_mode)
        self.acl_result = result

        if service.enforcement_enabled and not result.allowed:
            return self.handle_no_permission(result)

        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

    def get_acl_object(self, request, *args, **kwargs):
        """
        Return the domain object to evaluate permissions against.

        Default implementation reuses ``get_object`` when available.
        """
        if hasattr(self, "get_object"):
            obj = self.get_object()  # type: ignore[attr-defined]
            return obj
        raise NotImplementedError("ACLPermissionMixin requires get_acl_object to be implemented.")

    def get_acl_service(self) -> ACLEvaluationService:
        if not hasattr(self, "_acl_service"):
            self._acl_service = ACLEvaluationService()
        return self._acl_service

    def get_object(self, *args, **kwargs):  # pragma: no cover - delegated to superclass
        if self._acl_cached_object is not None:
            return self._acl_cached_object
        obj = super().get_object(*args, **kwargs)  # type: ignore[misc]
        self._acl_cached_object = obj
        if hasattr(self, "object"):
            self.object = obj  # type: ignore[attr-defined]
        return obj

    def handle_no_permission(self, result: ACLCheckResult):
        return HttpResponseForbidden(self.permission_denied_message)


def require_acl_permission(
    get_object: Callable[..., Any],
    *,
    mode: str = "acl:Read",
    denial_message: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for function-based views that want to enforce ACL checks.

    Args:
        get_object: Callable returning the object to evaluate. Receives the same
            arguments as the wrapped view.
        mode: ACL mode required for access (defaults to ``acl:Read``).
        denial_message: Optional override for the denied response text.
    """

    def decorator(view_func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            target = get_object(request, *args, **kwargs)
            if target is None:
                raise PermissionDenied(_("Unable to determine the object to authorise."))

            service = ACLEvaluationService()
            result = service.evaluate(request.user, target, mode=mode)

            if service.enforcement_enabled and not result.allowed:
                message = denial_message or _("You do not have permission to access this resource.")
                return HttpResponseForbidden(message)

            request.acl_result = result  # type: ignore[attr-defined]
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
