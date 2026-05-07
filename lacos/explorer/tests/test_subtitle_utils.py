from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from lacos.explorer.views.utils.subtitle import (
    find_subtitle_for_collection_video,
    find_subtitle_for_video,
)


def _make_resource(file_name, resource_id=None, mime_type=None, file_pid=None):
    return SimpleNamespace(
        id=resource_id or file_name,
        file_name=file_name,
        mime_type=mime_type or "",
        file_pid=file_pid,
    )


def _make_bundle_with_resources(resources):
    """Create a mock bundle whose iter_bundle_resources yields *resources*."""
    bundle = MagicMock()
    bundle._test_resources = resources
    return bundle


@patch("lacos.explorer.views.utils.subtitle.resolve_resource_to_presigned")
@patch("lacos.explorer.views.utils.subtitle.iter_bundle_resources")
def test_finds_matching_srt(mock_iter, mock_resolve):
    video = _make_resource("interview.mp4", resource_id="vid-1")
    subtitle = _make_resource("interview.srt", resource_id="sub-1")

    mock_iter.return_value = [video, subtitle]
    mock_resolve.return_value = {"bucket": "b", "key": "k", "url": "https://s3/interview.srt"}

    service = MagicMock()
    result = find_subtitle_for_video(MagicMock(), video, service, None)

    assert result == "https://s3/interview.srt"
    mock_resolve.assert_called_once()


@patch("lacos.explorer.views.utils.subtitle.resolve_resource_to_presigned")
@patch("lacos.explorer.views.utils.subtitle.iter_bundle_resources")
def test_returns_none_when_no_subtitle(mock_iter, mock_resolve):
    video = _make_resource("interview.mp4", resource_id="vid-1")
    other = _make_resource("notes.txt", resource_id="txt-1")

    mock_iter.return_value = [video, other]

    result = find_subtitle_for_video(MagicMock(), video, MagicMock(), None)

    assert result is None
    mock_resolve.assert_not_called()


@patch("lacos.explorer.views.utils.subtitle.resolve_resource_to_presigned")
@patch("lacos.explorer.views.utils.subtitle.iter_bundle_resources")
def test_case_insensitive_stem_match(mock_iter, mock_resolve):
    video = _make_resource("Interview.MP4", resource_id="vid-1")
    subtitle = _make_resource("interview.srt", resource_id="sub-1")

    mock_iter.return_value = [video, subtitle]
    mock_resolve.return_value = {"bucket": "b", "key": "k", "url": "https://s3/sub"}

    result = find_subtitle_for_video(MagicMock(), video, MagicMock(), None)

    assert result == "https://s3/sub"


@patch("lacos.explorer.views.utils.subtitle.resolve_resource_to_presigned")
@patch("lacos.explorer.views.utils.subtitle.iter_bundle_resources")
def test_skips_non_matching_subtitle(mock_iter, mock_resolve):
    video = _make_resource("interview.mp4", resource_id="vid-1")
    subtitle = _make_resource("other_file.srt", resource_id="sub-1")

    mock_iter.return_value = [video, subtitle]

    result = find_subtitle_for_video(MagicMock(), video, MagicMock(), None)

    assert result is None
    mock_resolve.assert_not_called()


@patch("lacos.explorer.views.utils.subtitle.resolve_resource_to_presigned")
@patch("lacos.explorer.views.utils.subtitle.iter_bundle_resources")
def test_returns_none_when_resolve_fails(mock_iter, mock_resolve):
    video = _make_resource("interview.mp4", resource_id="vid-1")
    subtitle = _make_resource("interview.srt", resource_id="sub-1")

    mock_iter.return_value = [video, subtitle]
    mock_resolve.return_value = None

    result = find_subtitle_for_video(MagicMock(), video, MagicMock(), None)

    assert result is None


@patch("lacos.explorer.views.utils.subtitle.resolve_collection_metadata_to_presigned")
def test_finds_collection_metadata_matching_srt(mock_resolve):
    video = _make_resource("interview.mp4", resource_id="vid-1")
    subtitle = _make_resource("interview.srt", resource_id="sub-1")
    structural_info = SimpleNamespace(
        additional_metadata_files=SimpleNamespace(all=lambda: [video, subtitle]),
    )
    collection = MagicMock()
    service = MagicMock()

    mock_resolve.return_value = {
        "bucket": "b",
        "key": "k",
        "url": "https://s3/interview.srt",
    }

    result = find_subtitle_for_collection_video(
        collection,
        structural_info,
        video,
        service,
    )

    assert result == "https://s3/interview.srt"
    mock_resolve.assert_called_once_with(service, subtitle, collection)


@patch("lacos.explorer.views.utils.subtitle.resolve_collection_metadata_to_presigned")
def test_collection_metadata_subtitle_requires_matching_stem(mock_resolve):
    video = _make_resource("interview.mp4", resource_id="vid-1")
    subtitle = _make_resource("other.srt", resource_id="sub-1")
    structural_info = SimpleNamespace(additional_metadata_files=[video, subtitle])

    result = find_subtitle_for_collection_video(
        MagicMock(),
        structural_info,
        video,
        MagicMock(),
    )

    assert result is None
    mock_resolve.assert_not_called()
