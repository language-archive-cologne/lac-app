from lacos.explorer.media_utils import determine_media_type, guess_source_mime_type, is_media_type


def test_determine_media_type_detects_imdi_extension_as_xml():
    assert determine_media_type("application/octet-stream", "Wooinap_family_situation.imdi") == "xml"


def test_determine_media_type_detects_xml_mime_type():
    assert determine_media_type("application/xml", "metadata.unknown") == "xml"
    assert determine_media_type("application/x-cmdi+xml", "metadata.bin") == "xml"


def test_guess_source_mime_type_uses_xml_default_when_detected():
    assert guess_source_mime_type(None, "file-without-extension", "xml") == "application/xml"


def test_is_media_type_reports_xml_for_imdi_file():
    assert is_media_type("application/octet-stream", "sample.imdi", "xml") is True
