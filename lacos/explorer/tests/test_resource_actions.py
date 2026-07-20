import logging
from types import SimpleNamespace

import pytest
from django.http import Http404
from django.test import RequestFactory

from lacos.explorer.resource_actions import MAX_LOGGED_ACTION_LENGTH
from lacos.explorer.resource_actions import ensure_supported_resource_action


def test_supported_resource_action_does_not_log(caplog):
    request = RequestFactory().get("/resource/test/?action=view")
    request.user = SimpleNamespace(is_authenticated=False, pk=None)

    with caplog.at_level(logging.WARNING, logger="lacos.explorer.resource_actions"):
        ensure_supported_resource_action(
            request,
            action="view",
            container=SimpleNamespace(pk="collection-id", identifier="collection"),
            resource=SimpleNamespace(pk="resource-id", file_pid="hdl:test/resource"),
        )

    assert not caplog.records


def test_unsupported_resource_action_is_bounded_in_logs(caplog):
    request = RequestFactory().get("/resource/test/")
    request.user = SimpleNamespace(is_authenticated=False, pk=None)
    action = "x" * (MAX_LOGGED_ACTION_LENGTH + 50)

    with (
        caplog.at_level(logging.WARNING, logger="lacos.explorer.resource_actions"),
        pytest.raises(Http404, match="Unsupported action"),
    ):
        ensure_supported_resource_action(
            request,
            action=action,
            container=SimpleNamespace(pk="collection-id", identifier="collection"),
            resource=SimpleNamespace(pk="resource-id", file_pid="hdl:test/resource"),
        )

    record = caplog.records[0]
    assert record.resource_action == action[:MAX_LOGGED_ACTION_LENGTH]
    assert record.resource_action_length == len(action)
