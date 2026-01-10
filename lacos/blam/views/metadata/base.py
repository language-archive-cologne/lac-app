from typing import Any


def apply_audit_fields(instance: Any, user: Any) -> None:
    if hasattr(instance, "created_by") and instance._state.adding and not instance.created_by:
        instance.created_by = user
    if hasattr(instance, "updated_by"):
        instance.updated_by = user
