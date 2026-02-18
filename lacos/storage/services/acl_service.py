import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from botocore.exceptions import ClientError
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.cache import get_acl_entry, set_acl_entry, invalidate_acl_entry
from lacos.storage.services.base_storage_service import BaseStorageService
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.utils.acl import determine_access_level, extract_read_agents, normalize_permissions_data

logger = logging.getLogger(__name__)


@dataclass
class ACLResult:
    """Represents the outcome of a load/save operation for a single object."""

    obj: Any
    bucket: Optional[str]
    key: Optional[str]
    success: bool
    error: Optional[str] = None

    @property
    def object_type(self) -> str:
        return type(self.obj).__name__

    @property
    def object_id(self) -> Any:
        return getattr(self.obj, "pk", None)


# Backwards compatibility alias
ACLSyncResult = ACLResult


class ACLService(BaseStorageService):
    """
    Service for loading and saving ACL definitions between S3 and the database.

    - Load: Read acl.json from S3 into ACLPermissions table
    - Save: Write ACLPermissions data back to S3 as acl.json
    """

    def __init__(self, skip_bucket_check: bool = True):
        if getattr(self, "initialized", False):
            return

        super().__init__(skip_bucket_check=skip_bucket_check)

        self.resource_mapping = ResourceMappingService(skip_bucket_check=True)
        self.set_client_and_buckets(self.resource_mapping)

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.initialized = True

    # =========================================================================
    # LOAD: S3 -> DB
    # =========================================================================

    def load_all(self) -> list[ACLResult]:
        """
        Load ACLs from S3 for every Collection and Bundle.

        Returns:
            List of ACLResult describing the outcome for each object.
        """
        results: list[ACLResult] = []

        for collection in Collection.objects.all():
            results.append(self.load_collection(collection))

        for bundle in Bundle.objects.all():
            results.append(self.load_bundle(bundle))

        return results

    def load_collection(self, collection: Collection) -> ACLResult:
        """Load ACL from S3 for a single collection."""
        bucket = collection.import_bucket or self.production_bucket
        key = self._build_acl_key(collection)
        return self._load_object(collection, bucket, key)

    def load_bundle(self, bundle: Bundle) -> ACLResult:
        """Load ACL from S3 for a single bundle."""
        bucket = bundle.import_bucket or self.production_bucket
        key = self._build_acl_key(bundle)
        return self._load_object(bundle, bucket, key)

    def _load_object(self, obj: Any, bucket: Optional[str], key: Optional[str]) -> ACLResult:
        if not bucket or not key:
            message = "Unable to determine ACL location"
            self.logger.warning("%s for %s (%s)", message, type(obj).__name__, getattr(obj, "pk", "unknown"))
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error=message)

        permissions_data, found, error, source_info = self._fetch_acl(bucket, key)

        try:
            return self._persist_loaded_permissions(obj, bucket, key, permissions_data, found, error, source_info)
        except Exception as exc:
            self.logger.exception("Failed to load ACL for %s (%s): %s", type(obj).__name__, getattr(obj, "pk", "unknown"), exc)
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error=str(exc))

    def _persist_loaded_permissions(
        self,
        obj: Any,
        bucket: str,
        key: str,
        permissions_data: Optional[Sequence[dict[str, Any]]],
        found: bool,
        fetch_error: Optional[str],
        source_info: Optional[dict[str, Any]] = None,
    ) -> ACLResult:
        """Store loaded permissions data in the ACLPermissions table."""
        ct = ContentType.objects.get_for_model(obj)
        from_cache = bool(source_info and source_info.get("from_cache"))

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

            if found and fetch_error is None:
                # Normalize agent URIs to our urn:lacos: format
                normalized_data = normalize_permissions_data(permissions_data)
                record.permissions_data = normalized_data
                if not (from_cache and not created):
                    record.last_synced = timezone.now()
                    fields_to_update.update({"permissions_data", "last_synced"})

                access_level = determine_access_level(normalized_data or [])
                read_agents = extract_read_agents(normalized_data or [])
                if record.access_level != access_level:
                    record.access_level = access_level
                    fields_to_update.add("access_level")
                if record.read_agents != read_agents:
                    record.read_agents = read_agents
                    fields_to_update.add("read_agents")

            elif fetch_error:
                self.logger.error(
                    "Error parsing ACL JSON for %s (%s): %s",
                    type(obj).__name__, getattr(obj, "pk", "unknown"), fetch_error,
                )
            elif not found:
                self.logger.warning(
                    "ACL file missing for %s (%s) at %s/%s",
                    type(obj).__name__, getattr(obj, "pk", "unknown"), bucket, key,
                )

            if fields_to_update:
                record.save(update_fields=list(fields_to_update))

        return ACLResult(obj=obj, bucket=bucket, key=key, success=found and not fetch_error, error=fetch_error)

    # =========================================================================
    # SAVE: DB -> S3
    # =========================================================================

    def save_collection(self, collection: Collection) -> ACLResult:
        """Save ACL from DB to S3 for a single collection."""
        bucket = collection.import_bucket or self.production_bucket
        key = self._build_acl_key(collection)
        return self._save_object(collection, bucket, key)

    def save_bundle(self, bundle: Bundle) -> ACLResult:
        """Save ACL from DB to S3 for a single bundle."""
        bucket = bundle.import_bucket or self.production_bucket
        key = self._build_acl_key(bundle)
        return self._save_object(bundle, bucket, key)

    def save_permission(self, permission: ACLPermissions) -> ACLResult:
        """Save an ACLPermissions record back to S3."""
        obj = permission.content_object
        if obj is None:
            return ACLResult(obj=None, bucket=None, key=None, success=False, error="Content object not found")

        bucket = permission.ACL_file_bucket
        key = permission.ACL_file_key

        if not bucket or not key:
            # Try to determine location from object
            bucket = getattr(obj, "import_bucket", None) or self.production_bucket
            key = self._build_acl_key(obj)

        if not bucket or not key:
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error="Unable to determine ACL location")

        return self._write_acl_to_s3(obj, bucket, key, permission.permissions_data)

    def _save_object(self, obj: Any, bucket: Optional[str], key: Optional[str]) -> ACLResult:
        if not bucket or not key:
            message = "Unable to determine ACL location"
            self.logger.warning("%s for %s (%s)", message, type(obj).__name__, getattr(obj, "pk", "unknown"))
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error=message)

        # Get permissions from DB
        ct = ContentType.objects.get_for_model(obj)
        try:
            record = ACLPermissions.objects.get(content_type=ct, object_id=obj.pk)
        except ACLPermissions.DoesNotExist:
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error="No ACL record in database")

        return self._write_acl_to_s3(obj, bucket, key, record.permissions_data)

    def _write_acl_to_s3(
        self,
        obj: Any,
        bucket: str,
        key: str,
        permissions_data: Optional[Sequence[dict[str, Any]]],
    ) -> ACLResult:
        """Write permissions data to S3 as acl.json."""
        try:
            # Convert to JSON
            data = permissions_data if permissions_data else []
            json_content = json.dumps(data, indent=2)

            # Write to S3
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json_content.encode("utf-8"),
                ContentType="application/json",
            )

            # Invalidate cache
            invalidate_acl_entry(bucket, key)

            self.logger.info("Saved ACL to s3://%s/%s", bucket, key)
            return ACLResult(obj=obj, bucket=bucket, key=key, success=True)

        except ClientError as exc:
            error_msg = f"S3 error writing ACL: {exc}"
            self.logger.error(error_msg)
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error=error_msg)
        except Exception as exc:
            error_msg = f"Error writing ACL: {exc}"
            self.logger.exception(error_msg)
            return ACLResult(obj=obj, bucket=bucket, key=key, success=False, error=error_msg)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _fetch_acl(self, bucket: str, key: str) -> tuple[Optional[Sequence[dict[str, Any]]], bool, Optional[str], dict]:
        """Retrieve and parse an ACL JSON file from S3."""
        cached_entry = get_acl_entry(bucket, key)
        if cached_entry is not None:
            return (
                deepcopy(cached_entry.data),
                cached_entry.found,
                cached_entry.error,
                {"from_cache": True, "etag": cached_entry.etag, "last_modified": cached_entry.last_modified},
            )

        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                set_acl_entry(bucket, key, data=None, found=False, error=None, etag=None, last_modified=None)
                return None, False, None, {"from_cache": False}
            return None, False, f"S3 error retrieving ACL: {error_code or exc}", {"from_cache": False}

        raw = response["Body"].read()
        if not raw:
            data: Sequence[dict[str, Any]] = []
            set_acl_entry(bucket, key, data=data, found=True, error=None, etag=response.get("ETag"), last_modified=response.get("LastModified"))
            return data, True, None, {"from_cache": False, "etag": response.get("ETag"), "last_modified": response.get("LastModified")}

        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as json_error:
            return None, True, f"Invalid JSON content: {json_error}", {"from_cache": False}

        if not isinstance(data, list):
            return None, True, "ACL JSON must be a list of rule objects", {"from_cache": False}

        set_acl_entry(bucket, key, data=data, found=True, error=None, etag=response.get("ETag"), last_modified=response.get("LastModified"))
        return data, True, None, {"from_cache": False, "etag": response.get("ETag"), "last_modified": response.get("LastModified")}

    def _build_acl_key(self, obj: Any) -> Optional[str]:
        """Build the S3 key for an object's acl.json file."""
        base_prefix = self._resolve_object_prefix(obj)
        if not base_prefix:
            return None
        return f"{base_prefix.rstrip('/')}/acl.json"

    # Backwards compatibility
    _build_collection_acl_key = _build_acl_key
    _build_bundle_acl_key = _build_acl_key

    def _resolve_object_prefix(self, obj: Any) -> Optional[str]:
        """Determine the S3 prefix for an object."""
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
        cleaned = prefix.strip().strip('/')
        if not cleaned:
            return None

        # OCFL content paths include explicit version markers like
        # ".../v1/content/...". Trim only at that marker so regular path
        # segments starting with "v" (e.g. "veraa") are preserved.
        marker = re.search(r"/v\d+/content(?:/|$)", cleaned, flags=re.IGNORECASE)
        if marker and marker.start() > 0:
            cleaned = cleaned[:marker.start()]
            return cleaned

        # Legacy/non-OCFL imports may store the XML file path directly
        # (e.g. "collection/bundle/bundle.xml"). In that case ACL lives
        # next to the object root directory, so strip filename.
        filename_like_suffixes = (".xml", ".cmdi", ".imdi")
        if cleaned.lower().endswith(filename_like_suffixes):
            parent = cleaned.rsplit("/", 1)[0] if "/" in cleaned else ""
            cleaned = parent or cleaned

        return cleaned

    # =========================================================================
    # Backwards compatibility aliases
    # =========================================================================

    def sync_all(self) -> list[ACLResult]:
        """Deprecated: Use load_all() instead."""
        return self.load_all()

    def sync_collection(self, collection: Collection) -> ACLResult:
        """Deprecated: Use load_collection() instead."""
        return self.load_collection(collection)

    def sync_bundle(self, bundle: Bundle) -> ACLResult:
        """Deprecated: Use load_bundle() instead."""
        return self.load_bundle(bundle)


# Backwards compatibility alias
ACLSyncService = ACLService
