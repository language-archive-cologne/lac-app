"""Audit the audio derivatives and ELAN audio links of BLAM collections.

The audit reads S3 and writes only ``MediaDerivativeStatus`` and
``ElanMediaLink`` rows. It changes no S3 object. ELAN files are matched to
audio with the same functions as the Explorer resource page.
"""

import logging
from collections import Counter
from xml.etree import ElementTree as ET

from botocore.exceptions import ClientError
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleAdditionalMetadataFile
from lacos.explorer.media_utils import determine_media_type
from lacos.explorer.media_utils import is_annotation_file
from lacos.storage.models import ElanMediaLink
from lacos.storage.models.media_derivatives import ElanLinkStatus
from lacos.storage.services.media_derivative_recorder import record_check
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


def _explorer_utils():
    # The Explorer views package imports all views; load it only when used.
    from lacos.explorer.views.utils.elan import parse_elan_text
    from lacos.explorer.views.utils.elan import pick_elan_audio_resources
    from lacos.explorer.views.utils.resource import iter_bundle_resources
    from lacos.explorer.views.utils.storage import resolve_resource_to_presigned

    return (
        parse_elan_text,
        pick_elan_audio_resources,
        iter_bundle_resources,
        resolve_resource_to_presigned,
    )


def collection_of_bundle(bundle):
    structural_info = bundle.structural_info.select_related(
        "is_member_of_collection"
    ).first()
    return structural_info.is_member_of_collection if structural_info else None


class MediaAuditService:
    """Fill ``MediaDerivativeStatus`` and ``ElanMediaLink`` for bundles."""

    def __init__(self, resource_service=None, media_service=None):
        if resource_service is None:
            from lacos.storage.services.resource_mapping_service import (
                ResourceMappingService,
            )

            resource_service = ResourceMappingService(skip_bucket_check=True)
        self.resource_service = resource_service
        self.media_service = media_service or MediaProcessingService()
        self.counts: Counter = Counter()
        self._derivative_rows: dict[tuple[str, str], object] = {}

    def audit_collection(self, collection) -> Counter:
        bundles = (
            Bundle.objects.filter(structural_info__is_member_of_collection=collection)
            .distinct()
            .order_by("identifier")
        )
        for bundle in bundles:
            self.audit_bundle(bundle, collection)
        return self.counts

    def audit_all_collections(self, on_collection=None) -> Counter:
        """Audit every collection. An error in one collection is counted and logged."""
        from lacos.blam.models.collection.collection_repository import Collection

        for collection in Collection.objects.order_by("identifier"):
            if on_collection:
                on_collection(collection)
            try:
                self.audit_collection(collection)
            except Exception:
                self.counts["collection_errors"] += 1
                logger.exception(
                    "Media audit failed for collection %s", collection.identifier
                )
        return self.counts

    def audit_bundle(self, bundle, collection=None) -> Counter:
        collection = collection or collection_of_bundle(bundle)
        _, _, iter_bundle_resources, _ = _explorer_utils()
        for resource in iter_bundle_resources(bundle):
            if isinstance(resource, BundleAdditionalMetadataFile):
                continue
            mime_type = getattr(resource, "mime_type", None)
            file_name = getattr(resource, "file_name", None)
            if is_annotation_file(mime_type, file_name):
                self.audit_elan_resource(bundle, resource, collection)
            elif determine_media_type(mime_type, file_name) == "audio":
                self.audit_audio_resource(bundle, resource, collection)
        return self.counts

    def _resolve(self, resource, bundle, collection):
        *_, resolve_resource_to_presigned = _explorer_utils()
        return resolve_resource_to_presigned(
            self.resource_service, resource, bundle, collection
        )

    def _check_derivatives(self, bucket: str, s3_key: str, collection):
        cache_key = (bucket, s3_key)
        if cache_key not in self._derivative_rows:
            row = record_check(
                bucket,
                s3_key,
                media_service=self.media_service,
                collection=collection,
            )
            self._derivative_rows[cache_key] = row
            self.counts[f"derivatives_{row.status}"] += 1
        return self._derivative_rows[cache_key]

    def audit_audio_resource(self, bundle, resource, collection):
        resolution = self._resolve(resource, bundle, collection)
        if not resolution:
            self.counts["audio_no_location"] += 1
            logger.info(
                "Audio resource %s (%s) has no storage location",
                resource.id,
                resource.file_name,
            )
            return None
        return self._check_derivatives(
            resolution["bucket"], resolution["key"], collection
        )

    def _read_elan(self, bucket: str, s3_key: str) -> dict | None:
        parse_elan_text, *_ = _explorer_utils()
        try:
            response = self.resource_service.s3_client.get_object(
                Bucket=bucket, Key=s3_key
            )
            raw_bytes = response["Body"].read()
        except ClientError as exc:
            logger.warning("Cannot read ELAN file %s/%s: %s", bucket, s3_key, exc)
            return None
        text = raw_bytes.decode("utf-8", errors="replace")
        try:
            ET.fromstring(text)
        except ET.ParseError as exc:
            logger.warning("Cannot parse ELAN file %s/%s: %s", bucket, s3_key, exc)
            return None
        return parse_elan_text(text)

    def audit_elan_resource(self, bundle, resource, collection=None) -> ElanMediaLink:
        _, pick_elan_audio_resources, _, _ = _explorer_utils()
        collection = collection or collection_of_bundle(bundle)
        values = {
            "elan_file_name": resource.file_name,
            "bundle": bundle,
            "collection": collection,
            "elan_bucket": "",
            "elan_s3_key": "",
            "referenced_media": [],
            "audio_file_name": "",
            "audio_bucket": "",
            "audio_s3_key": "",
            "audio_derivative": None,
            "last_checked_at": timezone.now(),
        }

        elan_resolution = self._resolve(resource, bundle, collection)
        elan_data = None
        if elan_resolution:
            values["elan_bucket"] = elan_resolution["bucket"]
            values["elan_s3_key"] = elan_resolution["key"]
            elan_data = self._read_elan(
                elan_resolution["bucket"], elan_resolution["key"]
            )

        if elan_data is None:
            values["link_status"] = ElanLinkStatus.ELAN_UNREADABLE
        else:
            media_files = elan_data.get("media_files", [])
            values["referenced_media"] = media_files
            values.update(self._link_audio(bundle, resource, collection, elan_data))
            if "link_status" not in values:
                values["link_status"] = (
                    ElanLinkStatus.REFERENCED_FOUND
                    if media_files
                    else ElanLinkStatus.NAME_FALLBACK
                )

        link, _ = ElanMediaLink.objects.update_or_create(
            elan_content_type=ContentType.objects.get_for_model(resource),
            elan_object_id=str(resource.id),
            defaults=values,
        )
        self.counts[f"link_{link.link_status}"] += 1
        return link

    def _link_audio(self, bundle, resource, collection, elan_data: dict) -> dict:
        """Pick the audio as the Explorer resource page does.

        With media references, the first candidate with a location wins.
        Without them, the candidate with the most derivative files wins.
        """
        _, pick_elan_audio_resources, _, _ = _explorer_utils()
        candidates = pick_elan_audio_resources(bundle, resource, elan_data)
        if not candidates:
            if elan_data.get("media_files"):
                return {"link_status": ElanLinkStatus.REFERENCED_MISSING}
            return {"link_status": ElanLinkStatus.NO_AUDIO}

        best = None
        best_score = -1
        for candidate in candidates:
            resolution = self._resolve(candidate, bundle, collection)
            if not resolution:
                continue
            row = self._check_derivatives(
                resolution["bucket"], resolution["key"], collection
            )
            if elan_data.get("media_files"):
                best = (candidate, resolution, row)
                break
            score = _sidecar_score(row)
            if score > best_score:
                best_score = score
                best = (candidate, resolution, row)

        if best is None:
            return {
                "audio_file_name": candidates[0].file_name,
                "link_status": ElanLinkStatus.AUDIO_NO_LOCATION,
            }

        candidate, resolution, row = best
        return {
            "audio_file_name": candidate.file_name,
            "audio_bucket": resolution["bucket"],
            "audio_s3_key": resolution["key"],
            "audio_derivative": row,
        }


def _sidecar_score(row) -> int:
    """Same score as the Explorer: no peaks is 0, then one per derivative file."""
    if row.peaks_last_modified is None:
        return 0
    return (
        1
        + (row.spectrogram_last_modified is not None)
        + (row.pitch_last_modified is not None)
    )
