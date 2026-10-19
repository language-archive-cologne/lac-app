import pytest

from lacos.storage.models import ElanMediaLink
from lacos.storage.models import MediaDerivativeStatus
from lacos.storage.services.media_audit_service import MediaAuditService

from .conftest import FakeStorage
from .conftest import add_audio
from .conftest import add_elan
from .conftest import content_key
from .conftest import elan_xml
from .conftest import make_bundle
from .conftest import make_collection

pytestmark = pytest.mark.django_db


@pytest.fixture
def bundle():
    return make_bundle(make_collection())


@pytest.fixture
def service(fake_s3, media_service, resolve_by_name):
    return MediaAuditService(
        resource_service=FakeStorage(fake_s3), media_service=media_service
    )


def _link():
    return ElanMediaLink.objects.get()


def test_referenced_audio_is_linked_with_its_derivative_status(
    fake_s3, service, bundle
):
    add_elan(bundle, "s1.eaf")
    add_audio(bundle, "s1_audio.wav")
    fake_s3.put(content_key("s1.eaf"), body=elan_xml("file:///C:/data/s1_audio.wav"))
    fake_s3.put(content_key("s1_audio.wav"))
    fake_s3.put_derivatives(content_key("s1_audio.wav"))

    service.audit_bundle(bundle)

    link = _link()
    assert link.link_status == "referenced_found"
    assert link.audio_file_name == "s1_audio.wav"
    assert link.referenced_media == ["file:///C:/data/s1_audio.wav"]
    assert link.audio_derivative.status == "works"
    assert link.collection == bundle.structural_info.first().is_member_of_collection
    # The audio is checked once even though both the ELAN file and the
    # audio resource lead to it.
    assert MediaDerivativeStatus.objects.count() == 1


def test_name_fallback_without_media_reference(fake_s3, service, bundle):
    add_elan(bundle, "s2.eaf")
    add_audio(bundle, "s2.wav")
    fake_s3.put(content_key("s2.eaf"), body=elan_xml())
    fake_s3.put(content_key("s2.wav"))

    service.audit_bundle(bundle)

    link = _link()
    assert link.link_status == "name_fallback"
    assert link.audio_derivative.status == "missing"


def test_name_fallback_prefers_the_audio_with_most_derivatives(
    fake_s3, service, bundle
):
    add_elan(bundle, "s3.eaf")
    add_audio(bundle, "s3_a.wav")
    add_audio(bundle, "s3_b.wav")
    fake_s3.put(content_key("s3.eaf"), body=elan_xml())
    fake_s3.put(content_key("s3_a.wav"))
    fake_s3.put(content_key("s3_b.wav"))
    fake_s3.put_derivatives(content_key("s3_b.wav"))

    service.audit_bundle(bundle)

    assert _link().audio_file_name == "s3_b.wav"


def test_referenced_audio_missing(fake_s3, service, bundle):
    add_elan(bundle, "s4.eaf")
    add_audio(bundle, "other.wav")
    fake_s3.put(content_key("s4.eaf"), body=elan_xml("s4.wav"))

    service.audit_bundle(bundle)

    assert _link().link_status == "referenced_missing"


def test_wav_with_wrong_mime_type_is_not_linked_but_gets_a_status_row(
    fake_s3, service, bundle
):
    add_elan(bundle, "s5.eaf")
    add_audio(bundle, "s5.wav", mime_type="application/octet-stream")
    fake_s3.put(content_key("s5.eaf"), body=elan_xml("s5.wav"))
    fake_s3.put(content_key("s5.wav"))

    service.audit_bundle(bundle)

    assert _link().link_status == "referenced_missing"
    assert MediaDerivativeStatus.objects.get().s3_key == content_key("s5.wav")


def test_no_audio(fake_s3, service, bundle):
    add_elan(bundle, "s6.eaf")
    fake_s3.put(content_key("s6.eaf"), body=elan_xml())

    service.audit_bundle(bundle)

    assert _link().link_status == "no_audio"


def test_audio_without_storage_location(fake_s3, service, bundle):
    add_elan(bundle, "s7.eaf")
    add_audio(bundle, "s7.wav")
    fake_s3.put(content_key("s7.eaf"), body=elan_xml("s7.wav"))

    counts = service.audit_bundle(bundle)

    link = _link()
    assert link.link_status == "audio_no_location"
    assert link.audio_file_name == "s7.wav"
    assert counts["audio_no_location"] == 1


@pytest.mark.parametrize("body", [None, b"<ANNOTATION_DOCUMENT><broken"])
def test_elan_unreadable(fake_s3, service, bundle, body):
    add_elan(bundle, "s8.eaf")
    if body is not None:
        fake_s3.put(content_key("s8.eaf"), body=body)

    service.audit_bundle(bundle)

    assert _link().link_status == "elan_unreadable"


def test_audit_updates_the_existing_link(fake_s3, service, bundle, media_service):
    add_elan(bundle, "s9.eaf")
    add_audio(bundle, "s9.wav")
    fake_s3.put(content_key("s9.eaf"), body=elan_xml("s9.wav"))
    service.audit_bundle(bundle)
    assert _link().link_status == "audio_no_location"

    fake_s3.put(content_key("s9.wav"))
    service = MediaAuditService(
        resource_service=FakeStorage(fake_s3), media_service=media_service
    )
    service.audit_bundle(bundle)

    assert _link().link_status == "referenced_found"


def test_audit_collection_covers_all_bundles(fake_s3, service):
    collection = make_collection("col-2")
    for index in range(2):
        bundle = make_bundle(collection, identifier=f"b{index}")
        add_elan(bundle, f"e{index}.eaf")
        fake_s3.put(content_key(f"e{index}.eaf"), body=elan_xml())

    counts = service.audit_collection(collection)

    assert ElanMediaLink.objects.count() == 2
    assert counts["link_no_audio"] == 2
