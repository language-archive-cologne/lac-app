from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from lacos.users.tasks import refresh_shibboleth_metadata


def _mock_response(payload: bytes, status: int = 200) -> Mock:
    response = Mock()
    response.status = status
    response.read.return_value = payload

    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context


@patch("lacos.users.tasks.request.urlopen")
def test_refresh_shibboleth_metadata_writes_file(mock_urlopen, settings, tmp_path):
    settings.SAML_LOGIN_ENABLED = True
    settings.SAML_METADATA_REFRESH_ENABLED = True
    settings.SAML_METADATA_REFRESH_URL = "https://idp.example.com/shibboleth"
    settings.SAML_METADATA_REFRESH_PATH = str(tmp_path / "shibboleth.xml")

    xml_payload = (
        b"<?xml version=\"1.0\"?>"
        b"<EntityDescriptor xmlns=\"urn:oasis:names:tc:SAML:2.0:metadata\" "
        b"entityID=\"https://idp.rrz.uni-koeln.de/idp/shibboleth\"></EntityDescriptor>"
    )

    mock_urlopen.return_value = _mock_response(xml_payload)

    runner = getattr(refresh_shibboleth_metadata, "call_local", refresh_shibboleth_metadata)
    result = runner()

    assert result["success"] is True
    assert result["changed"] is True
    assert Path(settings.SAML_METADATA_REFRESH_PATH).read_bytes() == xml_payload


@patch("lacos.users.tasks.request.urlopen")
def test_refresh_shibboleth_metadata_skips_when_unchanged(
    mock_urlopen,
    settings,
    tmp_path,
):
    settings.SAML_LOGIN_ENABLED = True
    settings.SAML_METADATA_REFRESH_ENABLED = True
    settings.SAML_METADATA_REFRESH_URL = "https://idp.example.com/shibboleth"
    settings.SAML_METADATA_REFRESH_PATH = str(tmp_path / "shibboleth.xml")

    xml_payload = (
        b"<?xml version=\"1.0\"?>"
        b"<EntityDescriptor xmlns=\"urn:oasis:names:tc:SAML:2.0:metadata\" "
        b"entityID=\"https://idp.rrz.uni-koeln.de/idp/shibboleth\"></EntityDescriptor>"
    )

    Path(settings.SAML_METADATA_REFRESH_PATH).write_bytes(xml_payload)
    mock_urlopen.return_value = _mock_response(xml_payload)

    runner = getattr(refresh_shibboleth_metadata, "call_local", refresh_shibboleth_metadata)
    result = runner()

    assert result["success"] is True
    assert result["changed"] is False
