from django.conf import settings

from lacos.users.saml_config import DEFAULT_MDQ_URL
from lacos.users.saml_config import build_saml_endpoints
from lacos.users.saml_config import build_saml_metadata_sources


def test_saml_settings_publish_ka3_successor_entity_categories():
    assert settings.SAML_CONFIG["entity_category"] == [
        "https://refeds.org/category/code-of-conduct/v2",
        "http://refeds.org/category/research-and-scholarship",
        "http://clarin.eu/category/clarin-member",
    ]


def test_build_saml_endpoints_preserves_primary_and_deduplicates_additional_urls():
    endpoints = build_saml_endpoints(
        primary_url="https://lacos.uni-koeln.de/saml2/acs/",
        additional_urls=[
            " https://lac.uni-koeln.de/saml2/acs/ ",
            "https://lacos.uni-koeln.de/saml2/acs/",
            "",
        ],
        binding="urn:test:post",
    )

    assert endpoints == [
        ("https://lacos.uni-koeln.de/saml2/acs/", "urn:test:post"),
        ("https://lac.uni-koeln.de/saml2/acs/", "urn:test:post"),
    ]


def test_build_saml_metadata_sources_uses_mdq_by_default():
    metadata = build_saml_metadata_sources(
        local_paths=["/app/shibboleth.xml"],
        remote_urls=[],
        mdq_url=DEFAULT_MDQ_URL,
    )

    assert metadata == {
        "local": ["/app/shibboleth.xml"],
        "mdq": [{"url": DEFAULT_MDQ_URL}],
    }


def test_build_saml_metadata_sources_includes_mdq_cert_when_configured():
    metadata = build_saml_metadata_sources(
        local_paths=[],
        remote_urls=[],
        mdq_url=DEFAULT_MDQ_URL,
        mdq_cert_file="/etc/shibboleth/dfn-mdq.pem",
    )

    assert metadata == {
        "mdq": [{
            "url": DEFAULT_MDQ_URL,
            "cert": "/etc/shibboleth/dfn-mdq.pem",
        }],
    }


def test_build_saml_metadata_sources_falls_back_to_local_file_when_empty():
    metadata = build_saml_metadata_sources(
        local_paths=[],
        remote_urls=[],
        mdq_url="",
        fallback_local_path="/app/shibboleth.xml",
    )

    assert metadata == {"local": ["/app/shibboleth.xml"]}


def test_build_saml_metadata_sources_preserves_explicit_remote_urls():
    metadata = build_saml_metadata_sources(
        local_paths=[],
        remote_urls=[
            "https://metadata.example.org/one.xml",
            "https://metadata.example.org/two.xml",
        ],
        mdq_url="",
    )

    assert metadata == {
        "remote": [
            {"url": "https://metadata.example.org/one.xml"},
            {"url": "https://metadata.example.org/two.xml"},
        ],
    }
