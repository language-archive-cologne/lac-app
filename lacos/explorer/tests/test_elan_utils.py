import pytest

from lacos.blam.models import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource
from lacos.explorer.views.utils.elan import parse_elan_text
from lacos.explorer.views.utils.elan import pick_elan_audio_resource


def test_parse_elan_text_aligns_independent_tiers_with_same_interval():
    elan_text = """
    <ANNOTATION_DOCUMENT>
      <TIME_ORDER>
        <TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="1000" />
        <TIME_SLOT TIME_SLOT_ID="ts2" TIME_VALUE="2500" />
      </TIME_ORDER>
      <TIER TIER_ID="Source">
        <ANNOTATION>
          <ALIGNABLE_ANNOTATION
            ANNOTATION_ID="a1"
            TIME_SLOT_REF1="ts1"
            TIME_SLOT_REF2="ts2">
            <ANNOTATION_VALUE>Source text</ANNOTATION_VALUE>
          </ALIGNABLE_ANNOTATION>
        </ANNOTATION>
      </TIER>
      <TIER TIER_ID="Translation">
        <ANNOTATION>
          <ALIGNABLE_ANNOTATION
            ANNOTATION_ID="b1"
            TIME_SLOT_REF1="ts1"
            TIME_SLOT_REF2="ts2">
            <ANNOTATION_VALUE>Translation text</ANNOTATION_VALUE>
          </ALIGNABLE_ANNOTATION>
        </ANNOTATION>
      </TIER>
    </ANNOTATION_DOCUMENT>
    """

    result = parse_elan_text(elan_text)

    assert result["tier_headers"] == ["Source", "Translation"]
    assert len(result["annotations"]) == 1
    assert result["annotations"][0]["start"] == 1
    assert result["annotations"][0]["end"] == 2.5
    assert result["annotations"][0]["ordered_tiers"] == [
        {"name": "Source", "value": "Source text"},
        {"name": "Translation", "value": "Translation text"},
    ]


def test_parse_elan_text_keeps_independent_tiers_with_different_intervals_separate():
    elan_text = """
    <ANNOTATION_DOCUMENT>
      <TIME_ORDER>
        <TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="1000" />
        <TIME_SLOT TIME_SLOT_ID="ts2" TIME_VALUE="2000" />
        <TIME_SLOT TIME_SLOT_ID="ts3" TIME_VALUE="3000" />
      </TIME_ORDER>
      <TIER TIER_ID="Source">
        <ANNOTATION>
          <ALIGNABLE_ANNOTATION
            ANNOTATION_ID="a1"
            TIME_SLOT_REF1="ts1"
            TIME_SLOT_REF2="ts2">
            <ANNOTATION_VALUE>First</ANNOTATION_VALUE>
          </ALIGNABLE_ANNOTATION>
        </ANNOTATION>
      </TIER>
      <TIER TIER_ID="Translation">
        <ANNOTATION>
          <ALIGNABLE_ANNOTATION
            ANNOTATION_ID="b1"
            TIME_SLOT_REF1="ts2"
            TIME_SLOT_REF2="ts3">
            <ANNOTATION_VALUE>Second</ANNOTATION_VALUE>
          </ALIGNABLE_ANNOTATION>
        </ANNOTATION>
      </TIER>
    </ANNOTATION_DOCUMENT>
    """

    result = parse_elan_text(elan_text)

    assert len(result["annotations"]) == 2
    assert result["annotations"][0]["ordered_tiers"] == [
        {"name": "Source", "value": "First"},
        {"name": "Translation", "value": ""},
    ]
    assert result["annotations"][1]["ordered_tiers"] == [
        {"name": "Source", "value": ""},
        {"name": "Translation", "value": "Second"},
    ]


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
