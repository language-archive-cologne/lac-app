from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.contrib import auth
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.http import urlencode
from djangosaml2.views import AssertionConsumerServiceView
from djangosaml2.views import LoginView
from djangosaml2.views import MetadataView
from djangosaml2.views import _set_subject_id
from saml2.mdstore import MetaDataMDX

from lacos.users.saml_logging import build_acs_failure_log_context
from lacos.users.saml_metadata import add_request_initiator

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http import HttpResponse
    from saml2.config import SPConfig

logger = logging.getLogger(__name__)


class LacosLoginView(LoginView):
    """Accept CLARIN Discovery's selected IdP return parameter."""

    def get_sp_config(self, request: HttpRequest) -> SPConfig:
        conf = super().get_sp_config(request)
        selected_idp = request.GET.get("idp")
        if selected_idp and _metadata_contains_selected_idp_without_mdq(
            conf,
            selected_idp,
        ):
            _remove_mdq_metadata_stores(conf)
        return conf

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        selected_entity_id = request.GET.get("entityID")
        if selected_entity_id and "idp" not in request.GET:
            params = request.GET.copy()
            params.pop("entityID", None)
            params.pop("returnIDParam", None)
            params["idp"] = selected_entity_id
            return redirect(f"{request.path}?{urlencode(params, doseq=True)}")

        return super().get(request, *args, **kwargs)


def _metadata_contains_selected_idp_without_mdq(
    conf: SPConfig,
    selected_idp: str,
) -> bool:
    metadata_sources = getattr(getattr(conf, "metadata", None), "metadata", {})
    for metadata_source in metadata_sources.values():
        if isinstance(metadata_source, MetaDataMDX):
            continue
        try:
            metadata_source[selected_idp]
        except KeyError:
            continue
        else:
            return True
    return False


def _remove_mdq_metadata_stores(conf: SPConfig) -> None:
    metadata_sources = getattr(getattr(conf, "metadata", None), "metadata", None)
    if not isinstance(metadata_sources, dict):
        return
    for source_key, metadata_source in list(metadata_sources.items()):
        if isinstance(metadata_source, MetaDataMDX):
            del metadata_sources[source_key]


class LacosMetadataView(MetadataView):
    """Publish SP metadata extensions that pysaml2 does not emit natively."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        response = super().get(request, *args, **kwargs)
        response.content = add_request_initiator(
            response.content,
            location=getattr(settings, "SAML_REQUEST_INITIATOR_URL", ""),
        )
        return response


class LacosAssertionConsumerServiceView(AssertionConsumerServiceView):
    """Authenticate SAML responses that identify users by ePPN attributes."""

    def handle_acs_failure(
        self,
        request: HttpRequest,
        exception: Exception | None = None,
        status: int = 403,
        **kwargs: Any,
    ) -> HttpResponse:
        logger.warning(
            "SAML ACS failure",
            extra=build_acs_failure_log_context(
                request,
                exception=exception,
                status=status,
                session_info=kwargs.get("session_info"),
            ),
        )
        return super().handle_acs_failure(
            request,
            exception=exception,
            status=status,
            **kwargs,
        )

    def authenticate_user(
        self,
        request: HttpRequest,
        session_info: dict[str, Any],
        attribute_mapping: Any,
        create_unknown_user: Any,
        assertion_info: dict[str, Any],
    ) -> Any:
        """Authenticate a verified SAML response without requiring NameID."""
        logger.debug("Trying to authenticate the user. Session info: %s", session_info)

        user = auth.authenticate(
            request=request,
            session_info=session_info,
            attribute_mapping=attribute_mapping,
            create_unknown_user=create_unknown_user,
            assertion_info=assertion_info,
        )
        if user is None:
            logger.warning(
                "Could not authenticate user received in SAML Assertion.",
            )
            message = "No user could be authenticated."
            raise PermissionDenied(message)

        auth.login(self.request, user)
        name_id = session_info.get("name_id")
        if name_id is None:
            self._log_missing_name_id(user, session_info)
        else:
            _set_subject_id(request.saml_session, name_id)
        logger.debug("User %s authenticated via SSO.", user)

        self.post_login_hook(request, user, session_info)
        self.customize_session(user, session_info)

        return user

    def _log_missing_name_id(self, user: Any, session_info: dict[str, Any]) -> None:
        attributes = session_info.get("ava") or {}
        has_eppn = bool(
            attributes.get("eduPersonPrincipalName")
            or attributes.get("urn:oid:1.3.6.1.4.1.5923.1.1.1.6"),
        )
        logger.warning(
            "SAML response did not include NameID; continuing with "
            "attribute-based login.",
            extra={
                "issuer": session_info.get("issuer", ""),
                "user": getattr(user, "username", ""),
                "has_eppn": has_eppn,
            },
        )
