from django.conf import settings

from lacos.users.saml_config import DEFAULT_MDQ_URL
from lacos.users.saml_config import build_saml_endpoints
from lacos.users.saml_config import build_saml_metadata_sources


def test_saml_settings_publish_ka3_successor_entity_categories():
    assert settings.SAML_CONFIG["entity_category"] == [
        "http://www.geant.net/uri/dataprotection-code-of-conduct/v1",
        "https://refeds.org/category/code-of-conduct/v2",
        "http://refeds.org/category/research-and-scholarship",
        "http://clarin.eu/category/clarin-member",
    ]


def test_saml_settings_publish_clarin_metadata_qa_fields():
    sp_config = settings.SAML_CONFIG["service"]["sp"]

    assert settings.SAML_CONFIG["metadata_key_usage"] == "signing"
    assert settings.SAML_CONFIG["description"] == (
        "Digital archive for endangered-language and ethnographic research "
        "data at the University of Cologne.",
        "en",
    )
    assert sp_config["endpoints"]["discovery_response"] == [
        (
            settings.SAML_DISCOVERY_RESPONSE_URL,
            "urn:oasis:names:tc:SAML:profiles:SSO:idp-discovery-protocol",
        ),
    ]
    expected_request_initiator_url = (
        f"{settings.SAML_SP_BASE_URL.rstrip('/')}/saml2/login/"
    )
    assert expected_request_initiator_url == settings.SAML_REQUEST_INITIATOR_URL


def test_saml_settings_publish_complete_contacts_for_metadata_qa():
    contacts = {
        contact["contact_type"]: contact
        for contact in settings.SAML_CONFIG["contact_person"]
    }

    assert contacts["administrative"] == {
        "contact_type": "administrative",
        "given_name": "Francisco",
        "sur_name": "Mondaca",
        "email_address": ["mailto:mondaca@uni-koeln.de"],
    }
    assert contacts["technical"]["given_name"] == "Francisco"
    assert contacts["technical"]["sur_name"] == "Mondaca"
    assert contacts["support"] == {
        "contact_type": "support",
        "given_name": "LAC",
        "sur_name": "Helpdesk",
        "email_address": ["mailto:lac-helpdesk@uni-koeln.de"],
    }


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


def test_build_saml_metadata_sources_allows_remote_only_proxy_config():
    clarin_proxy_metadata_url = (
        "https://infra.clarin.eu/aai/"
        "prod_md_about_clarin_erics_proxy-idp.xml"
    )
    metadata = build_saml_metadata_sources(
        local_paths=["", "  "],
        remote_urls=[
            f" {clarin_proxy_metadata_url} ",
        ],
        mdq_url="",
        fallback_local_path="/app/shibboleth.xml",
    )

    assert metadata == {
        "remote": [
            {
                "url": clarin_proxy_metadata_url,
            },
        ],
    }
