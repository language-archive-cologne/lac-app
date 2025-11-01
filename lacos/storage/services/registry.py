import logging
import threading
from typing import Dict, Type, TypeVar

from lacos.storage.services.base_storage_service import BaseStorageService
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.collection_service import CollectionService
from lacos.storage.services.file_discovery_service import FileDiscoveryService
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.services.upload_service import UploadService
from lacos.storage.services.acl_sync_service import ACLSyncService

logger = logging.getLogger(__name__)

TService = TypeVar("TService", bound=BaseStorageService)

_REGISTRY_LOCK = threading.RLock()
_SERVICE_CACHE: Dict[Type[BaseStorageService], BaseStorageService] = {}


def get_base_storage_service(*, skip_bucket_check: bool = False) -> BaseStorageService:
    """
    Return the process-wide BaseStorageService singleton.

    Args:
        skip_bucket_check: Whether to skip MinIO bucket verification during initialisation.
    """
    with _REGISTRY_LOCK:
        instance = _SERVICE_CACHE.get(BaseStorageService)
        if instance is None or not getattr(instance, "initialized", False):
            with BaseStorageService.allow_registry_construction():
                instance = BaseStorageService(skip_bucket_check=skip_bucket_check)
            _SERVICE_CACHE[BaseStorageService] = instance

    if not skip_bucket_check:
        instance.ensure_buckets_checked()
    return instance


def get_bucket_service(*, skip_bucket_check: bool = False) -> BucketService:
    return _get_service(BucketService, skip_bucket_check=skip_bucket_check)


def get_collection_service(*, skip_bucket_check: bool = False) -> CollectionService:
    return _get_service(CollectionService, skip_bucket_check=skip_bucket_check)


def get_upload_service(*, skip_bucket_check: bool = False) -> UploadService:
    return _get_service(UploadService, skip_bucket_check=skip_bucket_check)


def get_resource_mapping_service(*, skip_bucket_check: bool = False) -> ResourceMappingService:
    return _get_service(ResourceMappingService, skip_bucket_check=skip_bucket_check)


def get_file_discovery_service(*, skip_bucket_check: bool = False) -> FileDiscoveryService:
    return _get_service(FileDiscoveryService, skip_bucket_check=skip_bucket_check)


def get_acl_sync_service(*, skip_bucket_check: bool = True) -> ACLSyncService:
    return _get_service(ACLSyncService, skip_bucket_check=skip_bucket_check)


def reset_storage_services(*classes: Type[BaseStorageService]) -> None:
    """
    Clear cached singleton instances so tests can exercise fresh initialisation.

    Args:
        classes: Optional subset of service classes to reset. If omitted, all known services are reset.
    """
    targets = set(classes) if classes else {
        BaseStorageService,
        BucketService,
        CollectionService,
        UploadService,
        ResourceMappingService,
        FileDiscoveryService,
        ACLSyncService,
    }

    with _REGISTRY_LOCK:
        for target in targets:
            BaseStorageService.clear_service_singleton(target)
            _SERVICE_CACHE.pop(target, None)

        if BaseStorageService in targets:
            BaseStorageService.reset_shared_state()


def _get_service(cls: Type[TService], *, skip_bucket_check: bool) -> TService:
    with _REGISTRY_LOCK:
        instance = _SERVICE_CACHE.get(cls)
        created = False
        if instance is None or not getattr(instance, "initialized", False):
            with BaseStorageService.allow_construction(f"registry:{cls.__name__}"):
                instance = cls(skip_bucket_check=skip_bucket_check)  # type: ignore[call-arg]
            _SERVICE_CACHE[cls] = instance
            created = True

    base = get_base_storage_service(skip_bucket_check=skip_bucket_check)
    base.set_client_and_buckets(instance)
    if not skip_bucket_check:
        instance.ensure_buckets_checked()

    if created:
        logger.debug("Registry initialised %s (skip_bucket_check=%s)", cls.__name__, skip_bucket_check)

    return instance
