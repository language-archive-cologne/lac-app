import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from botocore.exceptions import ClientError
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.base_storage_service import BaseStorageService
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.utils.acl import determine_access_level, extract_read_agents

logger = logging.getLogger(__name__)


@dataclass
class ACLSyncResult:
    """Represents the outcome of a sync operation for a single object."""

    obj: Any
    bucket: Optional[str]
    key: Optional[str]
    found: bool
    updated: bool
    error: Optional[str] = None

    @property
    def object_type(self) -> str:
        return type(self.obj).__name__

    @property
    def object_id(self) -> Any:
        return getattr(self.obj, "pk", None)


class ACLSyncService(BaseStorageService):
    """
    Service responsible for synchronising ACL definitions stored alongside OCFL
    objects into the `ACLPermissions` table.
    """

    def __init__(self, skip_bucket_check: bool = True):
        if getattr(self, "initialized", False):
            return

        super().__init__(skip_bucket_check=skip_bucket_check)

        # Share the same S3 client across dependent services to avoid redundant setup.
        self.resource_mapping = ResourceMappingService(skip_bucket_check=True)
        self.set_client_and_buckets(self.resource_mapping)

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.initialized = True

    # Public API -----------------------------------------------------------------
    def sync_all(self) -> list[ACLSyncResult]:
        """
        Synchronise ACLs for every Collection and Bundle.

        Returns:
            List of ACLSyncResult describing the outcome for each object.
        """
        results: list[ACLSyncResult] = []

        for collection in Collection.objects.all():
            results.append(self.sync_collection(collection))

        for bundle in Bundle.objects.select_related("structural_info__is_member_of_collection"):
            results.append(self.sync_bundle(bundle))

        return results

    def sync_collection(self, collection: Collection) -> ACLSyncResult:
        """Synchronise the ACL for a single collection."""
        bucket = collection.import_bucket or self.production_bucket
        key = self._build_collection_acl_key(collection)
        return self._sync_object(collection, bucket, key)

    def sync_bundle(self, bundle: Bundle) -> ACLSyncResult:
        """Synchronise the ACL for a single bundle."""
        bucket = bundle.import_bucket or self.production_bucket
        key = self._build_bundle_acl_key(bundle)
        return self._sync_object(bundle, bucket, key)

    # Internal helpers -----------------------------------------------------------
    def _sync_object(self, obj: Any, bucket: Optional[str], key: Optional[str]) -> ACLSyncResult:
        if not bucket or not key:
            message = "Unable to determine ACL location"
            self.logger.warning("%s for %s (%s)", message, type(obj).__name__, getattr(obj, "pk", "unknown"))
            return ACLSyncResult(obj=obj, bucket=bucket, key=key, found=False, updated=False, error=message)

        permissions_data, found, error = self._fetch_acl(bucket, key)

        try:
            result = self._persist_permissions(obj, bucket, key, permissions_data, found, error)
            return result
        except Exception as exc:  # Defensive: avoid crashing sync loop
            self.logger.exception("Failed to persist ACL for %s (%s): %s", type(obj).__name__, getattr(obj, "pk", "unknown"), exc)
            return ACLSyncResult(obj=obj, bucket=bucket, key=key, found=found, updated=False, error=str(exc))

    def _persist_permissions(
        self,
        obj: Any,
        bucket: str,
        key: str,
        permissions_data: Optional[Sequence[dict[str, Any]]],
        found: bool,
        fetch_error: Optional[str],
    ) -> ACLSyncResult:
        """
        Store the permissions data on the `ACLPermissions` record for the object.

        Args:
            obj: Collection or Bundle instance.
            bucket: S3 bucket where the ACL resides.
            key: S3 key to the ACL file.
            permissions_data: Parsed JSON permissions (list of dicts) or None.
            found: Whether the ACL file was located in storage.
            fetch_error: Optional error message from the fetch step.
        """
        ct = ContentType.objects.get_for_model(obj)

        with transaction.atomic():
            record, created = ACLPermissions.objects.get_or_create(
                content_type=ct,
                object_id=obj.pk,
                defaults={"ACL_file_bucket": bucket, "ACL_file_key": key},
            )

            fields_to_update: set[str] = set()

            if record.ACL_file_bucket != bucket:
                record.ACL_file_bucket = bucket
                fields_to_update.add("ACL_file_bucket")

            if record.ACL_file_key != key:
                record.ACL_file_key = key
                fields_to_update.add("ACL_file_key")

            updated = created or bool(fields_to_update)

            current_permissions: Sequence[dict[str, Any]] | None = record.permissions_data

            if found and fetch_error is None:
                record.permissions_data = permissions_data
                record.last_synced = timezone.now()
                fields_to_update.update({"permissions_data", "last_synced"})
                current_permissions = permissions_data
                updated = True
            elif fetch_error:
                # Keep existing permissions data, but surface the error.
                self.logger.error(
                    "Error parsing ACL JSON for %s (%s): %s",
                    type(obj).__name__,
                    getattr(obj, "pk", "unknown"),
                    fetch_error,
                )
            elif not found:
                self.logger.warning(
                    "ACL file missing for %s (%s) at %s/%s",
                    type(obj).__name__,
                    getattr(obj, "pk", "unknown"),
                    bucket,
                    key,
                )

            access_level = determine_access_level(current_permissions or [])
            read_agents = extract_read_agents(current_permissions or [])
            if record.access_level != access_level:
                record.access_level = access_level
                fields_to_update.add("access_level")
            if record.read_agents != read_agents:
                record.read_agents = read_agents
                fields_to_update.add("read_agents")

            if fields_to_update:
                record.save(update_fields=list(fields_to_update))

        return ACLSyncResult(
            obj=obj,
            bucket=bucket,
            key=key,
            found=found,
            updated=updated,
            error=fetch_error,
        )

    def _fetch_acl(self, bucket: str, key: str) -> tuple[Optional[Sequence[dict[str, Any]]], bool, Optional[str]]:
        """
        Retrieve and parse an ACL JSON file from S3.

        Returns:
            Tuple of (permissions_data, found, error_message)
        """
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                return None, False, None
            return None, False, f"S3 error retrieving ACL: {error_code or exc}"

        raw = response["Body"].read()
        if not raw:
            return [], True, None

        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as json_error:
            return None, True, f"Invalid JSON content: {json_error}"

        if not isinstance(data, list):
            return None, True, "ACL JSON must be a list of rule objects"

        return data, True, None

    def _build_collection_acl_key(self, collection: Collection) -> Optional[str]:
        base_prefix = self._resolve_object_prefix(collection)
        if not base_prefix:
            return None
        return f"{base_prefix.rstrip('/')}/acl.json"

    def _build_bundle_acl_key(self, bundle: Bundle) -> Optional[str]:
        base_prefix = self._resolve_object_prefix(bundle)
        if not base_prefix:
            return None
        return f"{base_prefix.rstrip('/')}/acl.json"

    def _resolve_object_prefix(self, obj: Any) -> Optional[str]:
        """
        Determine the S3 prefix for an object based on stored metadata or
        registered resource mappings.
        """
        candidate_prefixes = [
            getattr(obj, "import_object_key", None),
            self._get_registered_prefix(obj),
        ]

        for prefix in candidate_prefixes:
            normalized = self._normalize_prefix(prefix)
            if normalized:
                return normalized

        return None

    def _get_registered_prefix(self, obj: Any) -> Optional[str]:
        location = self.resource_mapping.get_s3_location(obj)
        if not location or not location.s3_key:
            return None
        return location.s3_key

    @staticmethod
    def _normalize_prefix(prefix: Optional[str]) -> Optional[str]:
        if not prefix:
            return None
        cleaned = prefix.strip()
        return cleaned if cleaned else None
