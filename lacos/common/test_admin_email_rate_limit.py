import logging

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from lacos.common.admin_email_rate_limit import AdminEmailRateLimitFilter
from lacos.common.admin_email_rate_limit import build_admin_email_fingerprint


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def make_record(
    *,
    name="django.request",
    pathname="/app/lacos/users/views.py",
    lineno=10,
    request=None,
    status_code=500,
):
    record = logging.LogRecord(
        name=name,
        level=logging.ERROR,
        pathname=pathname,
        lineno=lineno,
        msg="Internal Server Error",
        args=(),
        exc_info=None,
    )
    record.status_code = status_code
    if request is not None:
        record.request = request
    return record


def test_repeated_identical_admin_emails_are_suppressed(settings):
    settings.ADMIN_EMAIL_RATE_LIMIT_IDENTICAL_LIMIT = 1
    settings.ADMIN_EMAIL_RATE_LIMIT_TOTAL_LIMIT = 10
    filter_ = AdminEmailRateLimitFilter()
    record = make_record()

    assert filter_.filter(record) is True
    assert filter_.filter(record) is False


def test_total_admin_email_volume_is_capped(settings):
    settings.ADMIN_EMAIL_RATE_LIMIT_IDENTICAL_LIMIT = 10
    settings.ADMIN_EMAIL_RATE_LIMIT_TOTAL_LIMIT = 2
    filter_ = AdminEmailRateLimitFilter()

    assert filter_.filter(make_record(lineno=10)) is True
    assert filter_.filter(make_record(lineno=11)) is True
    assert filter_.filter(make_record(lineno=12)) is False


def test_disallowed_host_uses_tighter_limit(settings):
    settings.ADMIN_EMAIL_RATE_LIMIT_IDENTICAL_LIMIT = 10
    settings.ADMIN_EMAIL_RATE_LIMIT_TOTAL_LIMIT = 10
    settings.ADMIN_EMAIL_RATE_LIMIT_DISALLOWED_HOST_LIMIT = 1
    filter_ = AdminEmailRateLimitFilter()
    record = make_record(name="django.security.DisallowedHost", status_code="")

    assert filter_.filter(record) is True
    assert filter_.filter(record) is False


def test_filter_suppresses_email_when_cache_counter_fails(monkeypatch):
    filter_ = AdminEmailRateLimitFilter()
    monkeypatch.setattr(filter_, "_increment_counter", lambda key, timeout: None)

    assert filter_.filter(make_record()) is False


def test_fingerprint_excludes_query_strings_and_posted_secrets():
    request = RequestFactory().post(
        "/accounts/login/?token=query-secret",
        data={"login": "user@example.test", "password": "posted-secret"},
    )
    fingerprint = build_admin_email_fingerprint(make_record(request=request))

    assert "query-secret" not in fingerprint
    assert "posted-secret" not in fingerprint
    assert "user@example.test" not in fingerprint
