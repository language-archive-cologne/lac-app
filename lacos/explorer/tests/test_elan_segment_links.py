"""Shareable ELAN segment links rendered into the annotation table (issue #1).

A segment link is a W3C Media Fragments anchor on the resource's handle URL:

    https://hdl.handle.net/11341/<pid>#t=20.500,24.000&id=a2

Segment links are offered on the standalone resource page only. The HTMX modal
is injected into the bundle page, where the host URL owns the fragment.
"""

from django.template.loader import render_to_string

from lacos.explorer.templatetags.explorer_extras import segment_fragment

HANDLE = "https://hdl.handle.net/11341/0000-0000-0000-3233"


# ─── segment_fragment ────────────────────────────────────────────────────


def test_segment_fragment_carries_the_range_and_the_annotation_id():
    assert segment_fragment({"id": "a2", "start": 20.5, "end": 24.0}) == (
        "#t=20.500,24.000&id=a2"
    )


def test_segment_fragment_omits_an_absent_end_bound():
    assert segment_fragment({"id": "a2", "start": 20.5, "end": None}) == (
        "#t=20.500&id=a2"
    )


def test_segment_fragment_omits_an_absent_annotation_id():
    assert segment_fragment({"id": "", "start": 20.5, "end": 24.0}) == (
        "#t=20.500,24.000"
    )


def test_segment_fragment_is_empty_for_an_unaligned_annotation():
    assert segment_fragment({"id": "a2", "start": None, "end": None}) == ""


def test_segment_fragment_pads_offsets_to_milliseconds():
    assert segment_fragment({"id": "a1", "start": 0.0, "end": 4.2}) == (
        "#t=0.000,4.200&id=a1"
    )


def _elan_context(**overrides):
    annotations = [
        {
            "id": "a1",
            "start": 0.0,
            "end": 4.2,
            "tiers": {"Source": "first"},
            "ordered_tiers": [{"name": "Source", "value": "first"}],
            "value": "first",
        },
        {
            "id": "a2",
            "start": 20.5,
            "end": 24.0,
            "tiers": {"Source": "second"},
            "ordered_tiers": [{"name": "Source", "value": "second"}],
            "value": "second",
        },
    ]
    context = {
        "annotations": annotations,
        "tier_headers": ["Source"],
        "audio_url": "https://example.test/rec01.wav",
        "audio_file_name": "rec01.wav",
        "audio_bucket": "bucket",
        "audio_key": "rec01.wav",
    }
    context.update(overrides)
    return context


def _render(**overrides):
    context = {
        "resource_name": "rec01.eaf",
        "media_type": "elan",
        "mime_type": "text/x-eaf+xml",
        "elan_context": _elan_context(),
        "resource_play_url": "/resource/11341/0000-0000-0000-3233/?action=play",
        "segment_link_base": HANDLE,
    }
    context.update(overrides)
    return render_to_string(
        "explorer/partials/resource_modal_content.html",
        context,
    )


def test_annotation_rows_carry_an_anchor_id():
    body = _render()

    assert 'id="ann-a1"' in body
    assert 'id="ann-a2"' in body


def test_annotation_rows_carry_the_annotation_id_as_data():
    body = _render()

    assert 'data-annotation-id="a1"' in body
    assert 'data-annotation-id="a2"' in body


def test_copy_button_emits_the_handle_url_with_a_media_fragment():
    body = _render()

    assert f'data-copy-text="{HANDLE}#t=20.500,24.000&amp;id=a2"' in body


def test_copy_button_omits_the_end_bound_for_an_unaligned_end():
    annotations = _elan_context()["annotations"]
    annotations[1]["end"] = None

    body = _render(elan_context=_elan_context(annotations=annotations))

    assert f'data-copy-text="{HANDLE}#t=20.500&amp;id=a2"' in body


def test_rows_without_a_start_offset_get_no_copy_button():
    annotations = _elan_context()["annotations"]
    annotations[1]["start"] = None
    annotations[1]["end"] = None

    body = _render(elan_context=_elan_context(annotations=annotations))

    # The aligned row is still citable, so the omission is selective rather
    # than the whole feature being absent.
    assert "&amp;id=a1" in body
    assert "&amp;id=a2" not in body


def test_segment_links_render_in_the_htmx_modal_too():
    """The modal must offer segment links, not just the standalone page.

    The player-mode tabs (Simple / Spectrogram / F0) are hx-get links that swap
    the modal partial into the standalone page. When the modal lacked
    segment_link_base, clicking a tab silently dropped every copy button.

    This is safe because a segment link is an absolute handle URL: copying it
    from a modal yields a link that opens the standalone page at that segment.
    Only *consuming* location.hash is standalone-only.
    """
    body = _render()

    assert body.count('data-copy-text="https://hdl.handle.net') == 2
    assert f'data-copy-text="{HANDLE}#t=20.500,24.000&amp;id=a2"' in body


def test_segment_links_are_omitted_without_a_resolvable_handle():
    # No handle to cite against (e.g. a resource with no file_pid).
    body = _render(segment_link_base=None)

    assert "#t=" not in body
    # Row anchors are handle-independent and stay either way.
    assert 'data-annotation-id="a2"' in body
