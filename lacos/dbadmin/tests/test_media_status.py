import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.dbadmin.media_status import get_media_status_summary
from lacos.dbadmin.media_views import MediaStatusView
from lacos.storage.models import ElanMediaLink
from lacos.storage.models import MediaDerivativeStatus
from lacos.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _collection(identifier, title):
    collection = Collection.objects.create(identifier=identifier)
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=title,
        description="",
        version="1.0",
        location=CollectionLocation.objects.create(
            location_name="Site",
            region_name="R",
            country_name="C",
            country_code="TC",
        ),
    )
    return collection


@pytest.fixture
def data():
    totoli = _collection("totoli", "Totoli Archive")
    other = _collection("other", "Another Archive")
    for index, status in enumerate(["missing", "missing", "stale"]):
        MediaDerivativeStatus.objects.create(
            bucket="b",
            s3_key=f"t{index}.wav",
            status=status,
            collection=totoli,
        )
    MediaDerivativeStatus.objects.create(
        bucket="b", s3_key="o.wav", status="current", collection=other
    )
    bundle = Bundle.objects.create(identifier="bundle")
    ElanMediaLink.objects.create(
        elan_content_type=ContentType.objects.get_for_model(Bundle),
        elan_object_id="1",
        elan_file_name="a.eaf",
        bundle=bundle,
        collection=totoli,
        link_status="referenced_missing",
    )
    return totoli, other


def _cell(cells, status):
    return next(cell for cell in cells if cell["status"] == status)


def test_summary_counts_totals_and_collections(data):
    totoli, _ = data

    summary = get_media_status_summary()

    assert summary["audio_total"] == 4
    assert summary["elan_total"] == 1
    assert _cell(summary["derivative_totals"], "missing")["count"] == 2
    assert [row["title"] for row in summary["collections"]] == [
        "Another Archive",
        "Totoli Archive",
    ]
    row = summary["collections"][1]
    assert row["audio_total"] == 3
    assert row["elan_total"] == 1
    missing = _cell(row["derivatives"], "missing")
    assert missing["count"] == 2
    assert f"collection__id__exact={totoli.id}" in missing["url"]
    assert "status__exact=missing" in missing["url"]
    assert _cell(row["links"], "referenced_missing")["count"] == 1


def test_summary_without_data():
    summary = get_media_status_summary()

    assert summary["audio_total"] == 0
    assert summary["collections"] == []
    assert summary["last_checked"] is None


def test_view_renders_for_superuser(data):
    request = RequestFactory().get("/dbadmin/media/")
    request.user = UserFactory(is_superuser=True, is_staff=True)

    response = MediaStatusView.as_view()(request)

    content = response.content.decode()
    assert response.status_code == 200
    assert "Totoli Archive" in content
    assert "/admin/storage/mediaderivativestatus/?status__exact=missing" in content


def test_view_denies_regular_user():
    request = RequestFactory().get("/dbadmin/media/")
    request.user = UserFactory(is_superuser=False, is_staff=False)

    with pytest.raises(PermissionDenied):
        MediaStatusView.as_view()(request)
