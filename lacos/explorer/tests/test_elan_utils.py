import pytest

from lacos.blam.models import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource
from lacos.explorer.views.utils.elan import pick_elan_audio_resource


def _bundle_with_resources(*resources):
    bundle = Bundle.objects.create(identifier="BND-ELAN-AUDIO")
    resource_container = BundleResources.objects.create(bundle=bundle)
    for resource in resources:
        if isinstance(resource, MediaResource):
            resource_container.bundle_media_resources.add(resource)
        elif isinstance(resource, WrittenResource):
            resource_container.bundle_written_resources.add(resource)
        else:
            resource_container.bundle_other_resources.add(resource)
    return bundle


@pytest.mark.django_db
def test_pick_elan_audio_resource_matches_referenced_media_file():
    elan = WrittenResource.objects.create(
        file_name="session.eaf",
        file_pid="hdl:11341/00-ELAN",
        mime_type="text/x-eaf+xml",
    )
    audio = MediaResource.objects.create(
        file_name="session.wav",
        file_pid="hdl:11341/00-WAV",
        mime_type="audio/wav",
    )
    unrelated_audio = MediaResource.objects.create(
        file_name="other.wav",
        file_pid="hdl:11341/00-OTHER",
        mime_type="audio/wav",
    )
    bundle = _bundle_with_resources(audio, unrelated_audio, elan)

    result = pick_elan_audio_resource(
        bundle,
        elan,
        {"media_files": ["file:///archive/session.wav"]},
    )

    assert result == audio


@pytest.mark.django_db
def test_pick_elan_audio_resource_ignores_arbitrary_audio_for_missing_reference():
    elan = WrittenResource.objects.create(
        file_name="01-10-07-1_2_maternal_clans.eaf",
        file_pid="hdl:11341/0000-0000-0000-7153",
        mime_type="text/x-eaf+xml",
    )
    arbitrary_audio = MediaResource.objects.create(
        file_name="different_recording.wav",
        file_pid="hdl:11341/00-WAV",
        mime_type="audio/wav",
    )
    bundle = _bundle_with_resources(arbitrary_audio, elan)

    result = pick_elan_audio_resource(
        bundle,
        elan,
        {"media_files": ["missing_recording.wav"]},
    )

    assert result is None


@pytest.mark.django_db
def test_pick_elan_audio_resource_falls_back_to_same_stem_without_declared_media():
    elan = WrittenResource.objects.create(
        file_name="session.eaf",
        file_pid="hdl:11341/00-ELAN",
        mime_type="text/x-eaf+xml",
    )
    audio = MediaResource.objects.create(
        file_name="session.wav",
        file_pid="hdl:11341/00-WAV",
        mime_type="audio/wav",
    )
    bundle = _bundle_with_resources(audio, elan)

    result = pick_elan_audio_resource(bundle, elan, {"media_files": []})

    assert result == audio
