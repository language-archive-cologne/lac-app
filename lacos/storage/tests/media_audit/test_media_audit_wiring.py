"""The task, commands, nightly check and admin actions write the status tables."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.urls import reverse

from lacos.storage.media_audit_tasks import check_media_derivatives_periodic
from lacos.storage.media_tasks import generate_peaks_task
from lacos.storage.models import ElanMediaLink
from lacos.storage.models import MediaDerivativeStatus

from .conftest import BUCKET
from .conftest import add_elan
from .conftest import content_key
from .conftest import elan_xml
from .conftest import make_bundle
from .conftest import make_collection

pytestmark = pytest.mark.django_db
KEY = content_key("a.wav")


@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_generate_peaks_task_records_failure(MockService):
    MockService.return_value.generate_peaks.return_value = {
        "success": False,
        "error": "audiowaveform error",
    }

    generate_peaks_task.call_local(BUCKET, KEY)

    row = MediaDerivativeStatus.objects.get(bucket=BUCKET, s3_key=KEY)
    assert row.status == "failed"
    assert row.last_error == "audiowaveform error"


@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_generate_peaks_task_records_unexpected_exception(MockService):
    MockService.return_value.generate_peaks.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        generate_peaks_task.call_local(BUCKET, KEY)

    assert MediaDerivativeStatus.objects.get().status == "failed"


@patch("lacos.storage.media_tasks.record_generation")
@patch("lacos.storage.media_tasks.MediaProcessingService")
def test_generate_peaks_task_records_success(MockService, mock_record):
    result = {"success": True, "peaks_key": "p"}
    MockService.return_value.generate_peaks.return_value = result

    generate_peaks_task.call_local(BUCKET, KEY)

    mock_record.assert_called_once_with(
        BUCKET, KEY, result, media_service=MockService.return_value
    )


@patch("lacos.storage.management.commands.generate_peaks.record_generation")
@patch("lacos.storage.management.commands.generate_peaks.MediaProcessingService")
@patch("lacos.storage.management.commands.generate_peaks.BucketService")
def test_generate_peaks_inline_records_result(MockBucket, MockMedia, mock_record):
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": [{"Key": KEY}]}]
    MockBucket.return_value.s3_client.get_paginator.return_value = paginator
    MockMedia.return_value.derivatives_current.return_value = False
    result = {"success": True}
    MockMedia.return_value.generate_peaks.return_value = result

    call_command("generate_peaks", "--bucket", BUCKET, "--inline", stdout=MagicMock())

    mock_record.assert_called_once_with(
        BUCKET, KEY, result, media_service=MockMedia.return_value
    )


def test_audit_media_command_fills_links(fake_s3, media_service, resolve_by_name):
    from .conftest import FakeStorage

    collection = make_collection("cmd-col")
    bundle = make_bundle(collection)
    add_elan(bundle, "e.eaf")
    fake_s3.put(content_key("e.eaf"), body=elan_xml())

    with (
        patch(
            "lacos.storage.services.resource_mapping_service.ResourceMappingService",
            return_value=FakeStorage(fake_s3),
        ),
        patch(
            "lacos.storage.services.media_audit_service.MediaProcessingService",
            return_value=media_service,
        ),
    ):
        call_command("audit_media", "--collection", "cmd-col", stdout=MagicMock())

    assert ElanMediaLink.objects.get().link_status == "no_audio"


def test_nightly_check_updates_status_and_continues_after_errors(
    fake_s3, media_service
):
    MediaDerivativeStatus.objects.create(bucket=BUCKET, s3_key=KEY)
    MediaDerivativeStatus.objects.create(
        bucket=BUCKET, s3_key="col/bundle/content/b.wav"
    )
    fake_s3.put(KEY)
    fake_s3.put_derivatives(KEY)
    original_head = fake_s3.head_object

    def head(Bucket, Key):
        if Key.endswith("b.wav"):
            raise RuntimeError("timeout")
        return original_head(Bucket=Bucket, Key=Key)

    fake_s3.head_object = head
    with patch(
        "lacos.storage.media_audit_tasks.MediaProcessingService",
        return_value=media_service,
    ):
        result = check_media_derivatives_periodic.call_local()

    assert result["works"] == 1
    assert result["errors"] == 1
    assert MediaDerivativeStatus.objects.get(s3_key=KEY).status == "works"


def test_admin_actions_queue_tasks(admin_client):
    row = MediaDerivativeStatus.objects.create(bucket=BUCKET, s3_key=KEY)
    url = reverse("admin:storage_mediaderivativestatus_changelist")

    with patch("lacos.storage.admin_media.generate_peaks_task") as mock_generate:
        admin_client.post(
            url, {"action": "regenerate_derivatives", "_selected_action": [row.pk]}
        )
    mock_generate.assert_called_once_with(BUCKET, KEY)

    with patch("lacos.storage.admin_media.recheck_derivatives_task") as mock_recheck:
        admin_client.post(url, {"action": "recheck", "_selected_action": [row.pk]})
    mock_recheck.assert_called_once_with([str(row.pk)])


def test_admin_changelists_render_with_filters(admin_client):
    for model in ("mediaderivativestatus", "elanmedialink"):
        response = admin_client.get(reverse(f"admin:storage_{model}_changelist"))
        assert response.status_code == 200
