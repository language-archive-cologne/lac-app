"""Verify production logging wiring without importing the settings module.

The production settings module reads required environment variables and mutates
shared state at import time, so we parse the ``LOGGING`` literal statically with
``ast`` instead (mirroring ``tests/test_production_saml_compose.py``).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _production_logging() -> dict[str, Any]:
    source = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "settings"
        / "production.py"
    ).read_text()
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "LOGGING"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("LOGGING assignment not found in production settings")


def test_saml_acs_failures_are_routed_to_admin_email():
    logging_config = _production_logging()

    saml_logger = logging_config["loggers"]["lacos.users.saml_views"]

    assert "mail_admins" in saml_logger["handlers"]


def test_saml_logger_still_emits_warnings_to_the_console():
    """Only ERROR should page admins; WARNING diagnostics must stay in logs.

    ``handle_acs_failure`` logs at ERROR, but missing-NameID and
    "could not authenticate" cases stay at WARNING. The logger level must not
    suppress those, and the ERROR-only email gate lives on the handler.
    """
    logging_config = _production_logging()

    saml_logger = logging_config["loggers"]["lacos.users.saml_views"]

    assert "console" in saml_logger["handlers"]
    assert saml_logger["level"] in {"DEBUG", "INFO", "WARNING"}


def test_admin_email_handler_only_pages_on_errors_and_keeps_rate_limit():
    logging_config = _production_logging()

    mail_admins = logging_config["handlers"]["mail_admins"]

    assert mail_admins["level"] == "ERROR"
    assert "admin_email_rate_limit" in mail_admins["filters"]


def test_loggers_with_admin_email_handlers_log_once_and_keep_console_output():
    logging_config = _production_logging()

    for logger_name, logger_config in logging_config["loggers"].items():
        if "mail_admins" in logger_config.get("handlers", []):
            assert logger_config["propagate"] is False, logger_name
            assert "console" in logger_config["handlers"], logger_name
