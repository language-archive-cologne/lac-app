import pytest

from lacos.blam.models import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource
from lacos.explorer.views.utils.resource import prepare_resource_lists


@pytest.mark.django_db
def test_prepare_resource_lists_shows_elan_media_relation_as_written_resource():
    bundle = Bundle.objects.create(identifier="BND-ELAN")
    resources = BundleResources.objects.create(bundle=bundle)
    elan = MediaResource.objects.create(
        file_name="session.eaf",
        file_pid="hdl:11341/00-ELAN",
        mime_type="text/x-eaf+xml",
        file_length="",
    )
    audio = MediaResource.objects.create(
        file_name="session.wav",
        file_pid="hdl:11341/00-WAV",
        mime_type="audio/wav",
        file_length="00:01:00",
    )
    resources.bundle_media_resources.add(elan, audio)

    media, written, other = prepare_resource_lists(resources)

    assert [resource.file_name for resource in media] == ["session.wav"]
    assert [resource.file_name for resource in written] == ["session.eaf"]
    assert other == []


@pytest.mark.django_db
def test_prepare_resource_lists_keeps_elan_written_relation_as_written_resource():
    bundle = Bundle.objects.create(identifier="BND-ELAN-WRITTEN")
    resources = BundleResources.objects.create(bundle=bundle)
    elan = WrittenResource.objects.create(
        file_name="session.elan",
        file_pid="hdl:11341/00-ELAN-WRITTEN",
        mime_type="application/xml",
    )
    resources.bundle_written_resources.add(elan)

    media, written, other = prepare_resource_lists(resources)

    assert media == []
    assert [resource.file_name for resource in written] == ["session.elan"]
    assert other == []
