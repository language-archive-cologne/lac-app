from unittest.mock import patch

from lacos.common.mixins.htmx_template_helpers import ROOT_FOLDER_SENTINEL
from lacos.storage.services.collection_service import BucketListingPage
from lacos.storage.views.dashboard.archivist import load_folder_contents


@patch("lacos.storage.views.dashboard.archivist.BucketService")
@patch("lacos.storage.views.dashboard.archivist.render")
def test_load_folder_contents_preserves_route_bucket_type_for_template_urls(
    mock_render, mock_bucket_service, prepared_request
):
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = "workspace-ingest-bucket"
    mock_instance.production_bucket = "workspace-production-bucket"
    mock_instance.dashboard_page_size = 50
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_all_accessible_buckets.return_value = ["workspace-ingest-bucket"]
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[],
        has_more=True,
        next_token="next-token",
        bucket="workspace-ingest-bucket",
        prefix="collection-a/",
    )

    request = prepared_request(
        "/storage/dashboard/folder-contents/ingest/collection-a//",
        method="get",
        data={"continuation_token": "next-token", "max_keys": "25"},
    )

    load_folder_contents(request, "ingest", "collection-a/")

    mock_instance.get_folder_contents.assert_called_once_with(
        "workspace-ingest-bucket",
        "collection-a/",
        max_keys=25,
        continuation_token="next-token",
        force_fresh=False,
        raise_errors=True,
    )

    context = mock_render.call_args[0][2]
    assert context["bucket_type"] == "ingest"
    assert context["folder_path"] == "collection-a/"
    assert context["folder_path_param"] == "collection-a/"
    assert context["max_keys"] == 25
    assert context["is_root"] is False


@patch("lacos.storage.views.dashboard.archivist.BucketService")
@patch("lacos.storage.views.dashboard.archivist.render")
def test_load_folder_contents_keeps_root_sentinel_for_load_more_url(
    mock_render, mock_bucket_service, prepared_request
):
    mock_instance = mock_bucket_service.return_value
    mock_instance.dashboard_page_size = 200
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_all_accessible_buckets.return_value = ["wooi_archive_cologne"]
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[],
        has_more=True,
        next_token="token-2",
        bucket="wooi_archive_cologne",
        prefix="",
    )

    request = prepared_request(
        f"/storage/dashboard/folder-contents/wooi_archive_cologne/{ROOT_FOLDER_SENTINEL}/",
        method="get",
    )

    load_folder_contents(request, "wooi_archive_cologne", ROOT_FOLDER_SENTINEL)

    mock_instance.get_folder_contents.assert_called_once_with(
        "wooi_archive_cologne",
        "",
        max_keys=200,
        continuation_token=None,
        force_fresh=False,
        raise_errors=True,
    )

    context = mock_render.call_args[0][2]
    assert context["bucket_type"] == "wooi_archive_cologne"
    assert context["folder_path"] == ""
    assert context["folder_path_param"] == ROOT_FOLDER_SENTINEL
    assert context["is_root"] is True


@patch("lacos.storage.views.dashboard.archivist.BucketService")
@patch("lacos.storage.views.dashboard.archivist.render")
def test_load_folder_contents_normalizes_folder_path_for_pagination_url(
    mock_render, mock_bucket_service, prepared_request
):
    mock_instance = mock_bucket_service.return_value
    mock_instance.dashboard_page_size = 100
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_all_accessible_buckets.return_value = ["wooi_archive_cologne"]
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[],
        has_more=True,
        next_token="token-3",
        bucket="wooi_archive_cologne",
        prefix="collections/wooi_archive_cologne/",
    )

    request = prepared_request(
        "/storage/dashboard/folder-contents/wooi_archive_cologne/collections//wooi_archive_cologne///",
        method="get",
    )

    load_folder_contents(
        request,
        "wooi_archive_cologne",
        "collections//wooi_archive_cologne//",
    )

    mock_instance.get_folder_contents.assert_called_once_with(
        "wooi_archive_cologne",
        "collections/wooi_archive_cologne/",
        max_keys=100,
        continuation_token=None,
        force_fresh=False,
        raise_errors=True,
    )

    context = mock_render.call_args[0][2]
    assert context["folder_path"] == "collections/wooi_archive_cologne/"
    assert context["folder_path_param"] == "collections/wooi_archive_cologne/"


@patch("lacos.storage.views.dashboard.archivist.BucketService")
@patch("lacos.storage.views.dashboard.archivist.render")
def test_load_folder_contents_retries_with_decoded_continuation_token(
    mock_render, mock_bucket_service, prepared_request
):
    mock_instance = mock_bucket_service.return_value
    mock_instance.dashboard_page_size = 100
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_all_accessible_buckets.return_value = ["wooi_archive_cologne"]
    listing = BucketListingPage(
        items=[],
        has_more=False,
        next_token=None,
        bucket="wooi_archive_cologne",
        prefix="collections/wooi_archive_cologne/",
    )
    mock_instance.get_folder_contents.side_effect = [
        Exception("Invalid continuation token"),
        listing,
    ]

    request = prepared_request(
        "/storage/dashboard/folder-contents/wooi_archive_cologne/collections/wooi_archive_cologne//",
        method="get",
        data={"continuation_token": "abc%2Fdef%3D"},
    )

    load_folder_contents(
        request,
        "wooi_archive_cologne",
        "collections/wooi_archive_cologne/",
    )

    assert mock_instance.get_folder_contents.call_count == 2
    first_call = mock_instance.get_folder_contents.call_args_list[0]
    second_call = mock_instance.get_folder_contents.call_args_list[1]

    assert first_call.kwargs["continuation_token"] == "abc%2Fdef%3D"
    assert second_call.kwargs["continuation_token"] == "abc/def="
    assert first_call.kwargs["raise_errors"] is True
    assert second_call.kwargs["raise_errors"] is True
    assert mock_render.call_args[0][1] == "dashboard/folder_contents_partial.html"


@patch("lacos.storage.views.dashboard.archivist.BucketService")
@patch("lacos.storage.views.dashboard.archivist.render")
def test_load_folder_contents_uses_error_partial_when_pagination_fails(
    mock_render, mock_bucket_service, prepared_request
):
    mock_instance = mock_bucket_service.return_value
    mock_instance.dashboard_page_size = 100
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_all_accessible_buckets.return_value = ["wooi_archive_cologne"]
    mock_instance.get_folder_contents.side_effect = Exception("S3 listing failed")

    request = prepared_request(
        "/storage/dashboard/folder-contents/wooi_archive_cologne/collections/wooi_archive_cologne//",
        method="get",
        data={"continuation_token": "token-1"},
    )

    load_folder_contents(
        request,
        "wooi_archive_cologne",
        "collections/wooi_archive_cologne/",
    )

    assert mock_render.call_args[0][1] == "dashboard/partials/folder_contents_error.html"
    assert "Failed to load folder contents" in mock_render.call_args[0][2]["error"]
