import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.constants import (
    ACL_LEVEL_RESTRICTED,
    WAC_AGENT,
    WAC_AUTHENTICATED_AGENT,
)
from lacos.storage.permissions import is_archivist
from lacos.storage.utils.acl import determine_access_level, normalize_agent_uri
from lacos.storage.models.acl_config import ACLConfig

logger = logging.getLogger(__name__)


@dataclass
class ACLCheckResult:
    """Represents the outcome of an ACL evaluation."""

    allowed: bool
    matched_rule: Optional[dict[str, Any]] = None
    source: Optional[Any] = None
    default_applied: bool = False
    reason: Optional[str] = None
    access_level: str = ACL_LEVEL_RESTRICTED

    def enforce(self) -> bool:
        """
        Return the effective decision after considering enforcement settings.

        When enforcement is disabled globally, callers should allow access even if
        this result is False. The service exposes enforcement flag separately.
        """
        return self.allowed


class ACLEvaluationService:
    """
    Evaluates whether a user may access an object based on synced ACL metadata.
    """

    def __init__(self):
        # Prefer DB-backed configuration; fall back to settings for defaults
        cfg = None
        try:
            cfg = ACLConfig.get_solo()
        except Exception:
            cfg = None

        self.enforcement_enabled = (
            cfg.enforcement_enabled if cfg is not None else getattr(settings, "ACL_ENFORCEMENT_ENABLED", True)
        )
        self.log_attempts = (
            cfg.log_access_attempts if cfg is not None else getattr(settings, "ACL_LOG_ACCESS_ATTEMPTS", True)
        )
        self.default_deny = (
            cfg.default_deny if cfg is not None else getattr(settings, "ACL_DEFAULT_DENY", True)
        )
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._content_type_cache: dict[type, ContentType] = {}

    # Public API ---------------------------------------------------------------
    def evaluate(self, user, obj: Any, mode: str = "acl:Read") -> ACLCheckResult:
        """
        Evaluate ACL access for a user/object pair and return the rich result.
        """
        result = self._evaluate_internal(user, obj, mode)

        if is_archivist(user) and not result.allowed:
            result.allowed = True
            result.reason = "Archivist override"

        if self.log_attempts:
            self._log_attempt(user, obj, mode, result)

        if not self.enforcement_enabled and not result.allowed:
            # When enforcement is disabled we still return the calculated result,
            # but make it clear in the logs that access will not be blocked.
            self.logger.debug(
                "ACL enforcement disabled; allowing access despite evaluation result: user=%s object=%s mode=%s",
                getattr(user, "pk", None),
                getattr(obj, "pk", None),
                mode,
            )

        return result

    def is_allowed(self, user, obj: Any, mode: str = "acl:Read") -> bool:
        """
        Convenience wrapper returning a boolean decision consistent with
        enforcement configuration.
        """
        result = self.evaluate(user, obj, mode)
        if not self.enforcement_enabled and not result.allowed:
            return True
        return result.allowed

    def can_read_bundle(self, user, bundle: Bundle) -> bool:
        return self.is_allowed(user, bundle, "acl:Read")

    def can_read_collection(self, user, collection: Collection) -> bool:
        return self.is_allowed(user, collection, "acl:Read")

    # Internal logic -----------------------------------------------------------
    def _evaluate_internal(self, user, obj: Any, mode: str) -> ACLCheckResult:
        last_source = None
        last_access_level = ACL_LEVEL_RESTRICTED
        for source in self._iter_acl_chain(obj):
            last_source = source
            permissions = self._get_permissions(source)
            if not permissions or not permissions.permissions_data:
                continue
            last_access_level = determine_access_level(permissions.permissions_data)

            matched_rule = self._match_rules(user, permissions.permissions_data, mode)
            if matched_rule:
                return ACLCheckResult(
                    allowed=True,
                    matched_rule=matched_rule,
                    source=source,
                    access_level=last_access_level,
                )

            # If ACL rules exist on the current object but none match, the
            # current object is authoritative for this mode and principal.
            # Do not fall back to parent ACLs in that case.
            return ACLCheckResult(
                allowed=False,
                matched_rule=None,
                source=source,
                default_applied=True,
                reason="No ACL rule matched on object; default deny",
                access_level=last_access_level,
            )

        return ACLCheckResult(
            allowed=False,
            matched_rule=None,
            source=last_source,
            default_applied=True,
            reason="No ACL data found; default deny",
            access_level=last_access_level,
        )

    def _iter_acl_chain(self, obj: Any) -> Iterable[Any]:
        seen: set[int] = set()
        current = obj
        while current is not None:
            current_id = id(current)
            if current_id in seen:
                break
            seen.add(current_id)
            yield current
            current = self._get_parent(current)

    @staticmethod
    def _get_parent(obj: Any) -> Optional[Any]:
        if hasattr(obj, "_acl_parent"):
            return getattr(obj, "_acl_parent")
        if isinstance(obj, Bundle):
            structural = getattr(obj, "structural_info", None)
            if structural and structural.exists():
                structural_info = structural.first()
                if structural_info:
                    return structural_info.is_member_of_collection
        return None

    def _get_permissions(self, obj: Any) -> Optional[ACLPermissions]:
        if hasattr(obj, "_acl_permissions"):
            return getattr(obj, "_acl_permissions")

        model_cls = obj.__class__
        content_type = self._content_type_cache.get(model_cls)
        if content_type is None:
            content_type = ContentType.objects.get_for_model(obj)
            self._content_type_cache[model_cls] = content_type

        return ACLPermissions.objects.filter(
            content_type=content_type,
            object_id=obj.pk,
        ).first()

    def _match_rules(self, user, rules: Sequence[dict[str, Any]], required_mode: str) -> Optional[dict[str, Any]]:
        for rule in rules:
            modes = rule.get("mode", [])
            if required_mode not in modes:
                continue

            if self._rule_applies(user, rule):
                return rule
        return None

    def _rule_applies(self, user, rule: dict[str, Any]) -> bool:
        agent_class = rule.get("agentClass")
        agent_uri = normalize_agent_uri(rule.get("agent"))

        if agent_class == WAC_AGENT:
            return True

        if agent_class == WAC_AUTHENTICATED_AGENT:
            return getattr(user, "is_authenticated", False)

        if agent_class == "foaf:Person":
            return bool(agent_uri and agent_uri in self._get_user_agent_uris(user))

        if agent_class == "foaf:Group":
            return bool(agent_uri and agent_uri in self._get_user_group_uris(user))

        # Backward compatibility for legacy ACL entries that stored only `agent`
        # without an explicit `agentClass`.
        if agent_uri:
            if agent_uri in self._get_user_agent_uris(user):
                return True
            if agent_uri in self._get_user_group_uris(user):
                return True

        return False

    @staticmethod
    def _is_authenticated(user) -> bool:
        return getattr(user, "is_authenticated", False)

    def _get_user_agent_uris(self, user) -> set[str]:
        if not self._is_authenticated(user):
            return set()

        uris = set()

        # Add the explicit ACL agent URI (urn:lacos:eppn:... or urn:lacos:user:...)
        acl_agent_uri = getattr(user, "acl_agent_uri", None)
        if acl_agent_uri:
            uris.add(acl_agent_uri.strip())

        username = getattr(user, "username", None)
        saml_persistent_id = getattr(user, "saml_persistent_id", None)
        if username:
            stripped = username.strip()
            if stripped:
                if saml_persistent_id:
                    uris.add(stripped)
                if "@" in stripped:
                    uris.add(f"urn:lacos:eppn:{stripped}")

        email = getattr(user, "email", None)
        if email:
            stripped = email.strip()
            if stripped:
                if saml_persistent_id:
                    uris.add(stripped)
                if "@" in stripped:
                    uris.add(f"urn:lacos:eppn:{stripped}")

        return {uri for uri in uris if uri}

    def _get_user_group_uris(self, user) -> set[str]:
        if not self._is_authenticated(user):
            return set()

        uris: set[str] = set()
        for group in user.groups.all():
            profile = getattr(group, "acl_profile", None)
            if profile and profile.acl_agent_uri:
                uris.add(profile.acl_agent_uri.strip())
            else:
                # Fallback to group name if no explicit ACL URI has been configured.
                if group.name:
                    uris.add(group.name.strip())
        return {uri for uri in uris if uri}

    def _log_attempt(self, user, obj: Any, mode: str, result: ACLCheckResult) -> None:
        user_repr = "anonymous" if isinstance(user, AnonymousUser) else getattr(user, "pk", getattr(user, "username", "unknown"))
        object_repr = f"{type(obj).__name__}:{getattr(obj, 'pk', 'unknown')}"
        rule_info = result.matched_rule or {}

        self.logger.info(
            "ACL check user=%s object=%s mode=%s allowed=%s default=%s rule=%s reason=%s",
            user_repr,
            object_repr,
            mode,
            result.allowed,
            result.default_applied,
            rule_info,
            result.reason,
        )
