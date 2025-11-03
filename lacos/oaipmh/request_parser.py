"""Parse and validate incoming OAI-PMH requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.http import HttpRequest

from .errors import OAIPMHError


@dataclass
class OAIRequest:
    verb: str
    metadata_prefix: Optional[str]
    identifier: Optional[str]
    resumption_token: Optional[str]
    set_spec: Optional[str]
    from_date: Optional[str]
    until_date: Optional[str]


class OAIRequestParser:
    """Extract and sanity-check standard OAI query parameters."""

    @staticmethod
    def parse(request: HttpRequest) -> OAIRequest:
        params = request.GET if request.method == "GET" else request.POST
        verb = params.get("verb")
        if not verb:
            raise OAIPMHError("badVerb", "Missing required 'verb' parameter")

        metadata_prefix = params.get("metadataPrefix")
        identifier = params.get("identifier")
        resumption_token = params.get("resumptionToken")
        set_spec = params.get("set")
        from_date = params.get("from")
        until_date = params.get("until")

        if resumption_token:
            # When resumptionToken is present no other arguments (except verb) are allowed.
            extraneous = [
                name
                for name, value in (
                    ("metadataPrefix", metadata_prefix),
                    ("identifier", identifier),
                    ("set", set_spec),
                    ("from", from_date),
                    ("until", until_date),
                )
                if value is not None
            ]
            if extraneous:
                raise OAIPMHError(
                    "badArgument",
                    "When resumptionToken is supplied no other arguments are permitted",
                )

        return OAIRequest(
            verb=verb,
            metadata_prefix=metadata_prefix,
            identifier=identifier,
            resumption_token=resumption_token,
            set_spec=set_spec,
            from_date=from_date,
            until_date=until_date,
        )
