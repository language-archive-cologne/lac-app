"""Tests for trusted-proxy client address resolution."""

from django.test import RequestFactory

from lacos.common.request_utils import get_client_ip


def test_client_ip_accepts_forwarded_address_from_trusted_proxy_network(settings):
    settings.TRUSTED_PROXY_IPS = []
    settings.TRUSTED_PROXY_CIDRS = ["172.16.0.0/12"]
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="172.19.0.1",
        HTTP_X_FORWARDED_FOR="203.0.113.25",
    )

    assert get_client_ip(request) == "203.0.113.25"


def test_client_ip_ignores_spoofed_header_from_untrusted_address(settings):
    settings.TRUSTED_PROXY_IPS = []
    settings.TRUSTED_PROXY_CIDRS = ["172.16.0.0/12"]
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="198.51.100.40",
        HTTP_X_FORWARDED_FOR="203.0.113.25",
    )

    assert get_client_ip(request) == "198.51.100.40"


def test_client_ip_preserves_exact_trusted_proxy_configuration(settings):
    settings.TRUSTED_PROXY_IPS = ["127.0.0.1"]
    settings.TRUSTED_PROXY_CIDRS = []
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_FORWARDED_FOR="203.0.113.25",
    )

    assert get_client_ip(request) == "203.0.113.25"


def test_client_ip_ignores_invalid_trusted_proxy_network(settings):
    settings.TRUSTED_PROXY_IPS = []
    settings.TRUSTED_PROXY_CIDRS = ["not-a-network"]
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="198.51.100.40",
        HTTP_X_FORWARDED_FOR="203.0.113.25",
    )

    assert get_client_ip(request) == "198.51.100.40"
