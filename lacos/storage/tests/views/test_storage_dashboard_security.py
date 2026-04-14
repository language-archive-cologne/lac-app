from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from lacos.blam.models.collection.collection_repository import Collection
from lacos.common.mixins.htmx_template_helpers import HtmxTemplateHelperMixin, ROOT_FOLDER_SENTINEL
from lacos.storage.services.collection_service import BucketListingPage
from lacos.storage.views.dashboard.archivist import bucket_size_info, load_folder_contents
from lacos.storage.views.dashboard.htmx.bucket import BucketContentHTMXView
from lacos.users.models import CollectionManagerAssignment
from lacos.users.tests.factories import UserFactory


def _ensure_group(name: str) -> Group:
    return Group.objects.get_or_create(name=name)[0]


def _make_collection_manager(collection_identifier: str) -> tuple:
    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))
    collection = Collection.objects.create(identifier=collection_identifier)
    CollectionManagerAssignment.objects.create(user=user, collection=collection)
    return user, collection


@pytest.mark.django_db
@patch("lacos.storage.views.dashboard.archivist.render")
@patch("lacos.storage.views.dashboard.archivist.BucketService")
def test_collection_manager_root_folder_listing_is_filtered(
    mock_bucket_service, mock_render
):
    user, _ = _make_collection_manager("collection-a")
    Collection.objects.create(identifier="collection-b")
    request = RequestFactory().get("/storage/dashboard/folder-contents/ingest/__root__/")
    request.user = user
    request.session = {}
    request.headers = {}

    mock_instance = mock_bucket_service.return_value
    mock_instance.workspace_buckets = ["ingest"]
    mock_instance.ingest_bucket = "ingest-bucket"
    mock_instance.production_bucket = "production-bucket"
    mock_instance.dashboard_page_size = 50
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_all_accessible_buckets.return_value = ["ingest-bucket", "private-bucket"]
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[
            {"type": "folder", "name": "collection-a", "path": "collection-a/"},
            {"type": "folder", "name": "collection-b", "path": "collection-b/"},
        ],
        has_more=False,
        next_token=None,
        bucket="ingest-bucket",
        prefix="",
    )

    load_folder_contents(request, "ingest", ROOT_FOLDER_SENTINEL)

    context = mock_render.call_args[0][2]
    assert [item["path"] for item in context["listing"].items] == ["collection-a/"]
    assert context["storage_dashboard_access"].can_use_archivist_tools is False


@pytest.mark.django_db
@patch("lacos.storage.views.dashboard.archivist.BucketService")
def test_collection_manager_unassigned_folder_is_denied(mock_bucket_service):
    user, _ = _make_collection_manager("collection-a")
    Collection.objects.create(identifier="collection-b")
    request = RequestFactory().get("/storage/dashboard/folder-contents/ingest/collection-b/")
    request.user = user
    request.session = {}
    request.headers = {}

    mock_instance = mock_bucket_service.return_value
    mock_instance.workspace_buckets = ["ingest"]
    mock_instance.ingest_bucket = "ingest-bucket"
    mock_instance.production_bucket = "production-bucket"
    mock_instance.get_all_accessible_buckets.return_value = ["ingest-bucket"]

    with pytest.raises(PermissionDenied):
        load_folder_contents(request, "ingest", "collection-b/subfolder/")


@pytest.mark.django_db
@patch("lacos.storage.views.dashboard.archivist.BucketService")
def test_collection_manager_bucket_size_is_denied(mock_bucket_service):
    user, _ = _make_collection_manager("collection-a")
    request = RequestFactory().get("/storage/dashboard/bucket-size/ingest-bucket/")
    request.user = user
    request.session = {}
    request.headers = {}

    mock_instance = mock_bucket_service.return_value
    mock_instance.workspace_buckets = ["ingest"]
    mock_instance.ingest_bucket = "ingest-bucket"
    mock_instance.production_bucket = "production-bucket"
    mock_instance.get_all_accessible_buckets.return_value = ["ingest-bucket"]

    with pytest.raises(PermissionDenied):
        bucket_size_info(request, "ingest-bucket")


class _DummyHelperView(HtmxTemplateHelperMixin):
    pass


@pytest.mark.django_db
@patch("lacos.common.mixins.htmx_template_helpers.render_to_string", return_value="rendered")
@patch("lacos.common.mixins.htmx_template_helpers.get_token", return_value="csrf-token")
@patch("lacos.storage.services.bucket_service.BucketService")
def test_collection_manager_bucket_content_root_listing_is_filtered(
    mock_bucket_service,
    _mock_get_token,
    mock_render_to_string,
):
    user, _ = _make_collection_manager("collection-a")
    Collection.objects.create(identifier="collection-b")
    request = RequestFactory().get("/storage/htmx/bucket-content/ingest-bucket/")
    request.user = user
    request.session = {}

    mock_instance = mock_bucket_service.return_value
    mock_instance.workspace_buckets = ["ingest"]
    mock_instance.ingest_bucket = "ingest-bucket"
    mock_instance.production_bucket = "production-bucket"
    mock_instance.ocfl_buckets = []
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.dashboard_page_size = 50
    mock_instance.get_all_accessible_buckets.return_value = ["ingest-bucket", "private-bucket"]
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[
            {"type": "folder", "name": "collection-a", "path": "collection-a/"},
            {"type": "folder", "name": "collection-b", "path": "collection-b/"},
        ],
        has_more=False,
        next_token=None,
        bucket="ingest-bucket",
        prefix="",
    )

    view = _DummyHelperView()
    html = view.render_bucket_content_template(request, "ingest-bucket")

    assert html == "rendered"
    template_name, context = mock_render_to_string.call_args[0]
    assert template_name == "dashboard/bucket_content_partial.html"
    assert [item["path"] for item in context["listing"].items] == ["collection-a/"]
    assert context["storage_dashboard_access"].can_view_bucket_metrics is False


@pytest.mark.django_db
def test_collection_manager_bucket_content_htmx_view_is_allowed():
    user, _ = _make_collection_manager("collection-a")
    request = RequestFactory().get("/storage/htmx/bucket-content/ingest-bucket/")
    request.user = user
    request.session = {}
    request.headers = {"HX-Request": "true"}

    with patch.object(BucketContentHTMXView, "render_bucket_content_template", return_value="content"), patch.object(
        BucketContentHTMXView, "build_bucket_tabs_oob_response", return_value=""
    ):
        response = BucketContentHTMXView.as_view()(request, bucket_name="ingest-bucket")

    assert response.status_code == 200
