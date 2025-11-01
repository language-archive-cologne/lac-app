import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional, Generator
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class BaseStorageService:
    """
    Base service for interacting with S3/MinIO storage.
    
    This service handles both local development with MinIO and production with S3.
    It automatically detects the environment and configures the client accordingly.
    """
    
    # Class-level flag to track if buckets have been checked
    _buckets_checked = False
    _instance = None
    _instance_lock = threading.RLock()
    _shared_runtime_lock = threading.RLock()
    _shared_runtime: Optional[Dict[str, Any]] = None
    _construction_context = threading.local()
    _startup_complete = False
    _post_startup_initializations = set()
    _direct_instantiation_warnings = set()

    def __new__(cls, *args, **kwargs):
        if getattr(cls, "_instance", None) is None:
            lock = getattr(cls, "_instance_lock", None)
            if lock is None:
                lock = threading.RLock()
                setattr(cls, "_instance_lock", lock)
            with lock:
                if getattr(cls, "_instance", None) is None:
                    cls._instance = super(BaseStorageService, cls).__new__(cls)
        return cls._instance

    def __init__(self, skip_bucket_check: bool = False):
        if getattr(self, "initialized", False):
            return

        self._maybe_warn_direct_construction()

        runtime, created = self._get_or_create_runtime(skip_bucket_check=skip_bucket_check)
        self._apply_runtime(runtime)
        self._maybe_run_bucket_checks(skip_bucket_check, runtime)
        self.initialized = True
        self._record_service_initialized(created=created, source=self._current_construction_source())
        self._maybe_emit_post_startup_warning(created=created)

    def _get_or_create_runtime(self, skip_bucket_check: bool):
        runtime = self._get_shared_runtime_snapshot()
        if runtime is not None:
            return runtime, False

        with self._shared_runtime_lock:
            runtime = self._shared_runtime
            created = False
            if runtime is None:
                runtime = self._bootstrap_runtime(skip_bucket_check=skip_bucket_check)
                self._shared_runtime = runtime
                created = True
            return runtime, created

    @classmethod
    def _get_shared_runtime_snapshot(cls):
        with cls._shared_runtime_lock:
            return cls._shared_runtime

    def _bootstrap_runtime(self, skip_bucket_check: bool) -> Dict[str, Any]:
        logger.info("Initializing BaseStorageService...")

        self.is_minio = self._is_minio_environment()
        self.endpoint_url = self._get_endpoint_url()
        self.access_key = self._get_access_key()
        self.secret_key = self._get_secret_key()
        self.region = self._get_region()
        self.in_container = self._is_running_in_container()

        self.workspace_buckets = self._get_workspace_buckets()
        # OCFL buckets will be determined dynamically

        self.ingest_bucket = self._get_ingest_bucket_name()
        self.production_bucket = self._get_production_bucket_name()

        logger.info(f"Creating S3 client with endpoint URL: {self.endpoint_url}")
        self.s3_client = self._create_s3_client()

        logger.info(f"BaseStorageService initialized with {'MinIO' if self.is_minio else 'S3'}")
        logger.info(f"Using endpoint: {self.endpoint_url or 'default S3 endpoint'}")
        logger.info(f"Using region: {self.region}")
        logger.info(f"Workspace buckets: {self.workspace_buckets}")

        explicit_ingest = getattr(settings, 'S3_INGEST_BUCKET', None) or getattr(settings, 'AWS_INGEST_BUCKET_NAME', None)
        explicit_production = getattr(settings, 'S3_PRODUCTION_BUCKET', None) or getattr(settings, 'AWS_PRODUCTION_BUCKET_NAME', None)

        if explicit_ingest or explicit_production:
            logger.debug(f"Legacy bucket mappings: ingest={self.ingest_bucket}, production={self.production_bucket}")

        self._execute_bucket_checks(skip_bucket_check)

        self._bucket_cache_metadata = {}

        runtime = {
            "is_minio": self.is_minio,
            "endpoint_url": self.endpoint_url,
            "access_key": self.access_key,
            "secret_key": self.secret_key,
            "region": self.region,
            "in_container": self.in_container,
            "workspace_buckets": self.workspace_buckets,
            "ingest_bucket": self.ingest_bucket,
            "production_bucket": self.production_bucket,
            "s3_client": self.s3_client,
            "presigned_client": getattr(self, "presigned_client", self.s3_client),
            "buckets_checked": bool(getattr(self, "_buckets_checked", False)),
            "bucket_cache_metadata": self._bucket_cache_metadata,
        }
        return runtime

    def _apply_runtime(self, runtime: Dict[str, Any]) -> None:
        self.is_minio = runtime["is_minio"]
        self.endpoint_url = runtime["endpoint_url"]
        self.access_key = runtime["access_key"]
        self.secret_key = runtime["secret_key"]
        self.region = runtime["region"]
        self.in_container = runtime["in_container"]
        self.workspace_buckets = runtime["workspace_buckets"]
        self.ingest_bucket = runtime["ingest_bucket"]
        self.production_bucket = runtime["production_bucket"]
        self.s3_client = runtime["s3_client"]
        self.presigned_client = runtime.get("presigned_client") or self.s3_client
        self._buckets_checked = runtime.get("buckets_checked", False)
        metadata = runtime.get("bucket_cache_metadata")
        self._bucket_cache_metadata = dict(metadata) if metadata else {}

    def _maybe_run_bucket_checks(self, skip_bucket_check: bool, runtime: Dict[str, Any]) -> None:
        if skip_bucket_check:
            return
        if runtime.get("buckets_checked"):
            return
        if not self.is_minio:
            return
        self._execute_bucket_checks(False)
        self._update_shared_runtime("buckets_checked", bool(getattr(self, "_buckets_checked", False)))

    def ensure_buckets_checked(self) -> None:
        """Ensure MinIO workspace buckets are verified once per process."""
        if getattr(self, "_buckets_checked", False):
            return
        if not getattr(self, "is_minio", False):
            return
        self._execute_bucket_checks(False)
        self._update_shared_runtime("buckets_checked", bool(getattr(self, "_buckets_checked", False)))

    def _execute_bucket_checks(self, skip_bucket_check: bool) -> None:
        if not skip_bucket_check and not getattr(self, "_buckets_checked", False) and self.is_minio:
            allow_all = any(bucket in ("*", "__all__") for bucket in self.workspace_buckets)
            allow_all = allow_all or not self.workspace_buckets

            if not allow_all:
                logger.info("Ensuring workspace buckets exist...")
                buckets_to_check = [b for b in self.workspace_buckets if b not in ("*", "__all__")]

                for bucket_name in buckets_to_check:
                    bucket_exists = self.ensure_bucket_exists(bucket_name)
                    if bucket_exists:
                        logger.info(f"Ensuring CORS is configured for {bucket_name}...")
                        cors_result = self.ensure_cors_enabled(bucket_name)
                        if cors_result["success"]:
                            if cors_result.get("updated", False):
                                logger.info(f"✅ CORS configuration for {bucket_name} has been updated")
                            else:
                                logger.info(f"✅ CORS configuration for {bucket_name} is already correct")
                        else:
                            logger.warning(f"⚠️ Failed to configure CORS for {bucket_name}: {cors_result.get('error', 'Unknown error')}")
            else:
                logger.info("All buckets mode enabled - skipping bucket creation checks (buckets will be discovered dynamically)")

            self._buckets_checked = True
        elif not self.is_minio:
            logger.info("Skipping bucket checks for external S3 (buckets will be discovered dynamically)")

    @classmethod
    def _update_shared_runtime(cls, key: str, value: Any) -> None:
        with cls._shared_runtime_lock:
            if cls._shared_runtime is not None:
                cls._shared_runtime[key] = value

    def sync_shared_runtime_state(self) -> None:
        """Push mutable runtime fields back into the shared runtime cache."""
        self._update_shared_runtime("workspace_buckets", self.workspace_buckets)
        self._update_shared_runtime("ingest_bucket", self.ingest_bucket)
        self._update_shared_runtime("production_bucket", self.production_bucket)

    def _record_service_initialized(self, *, created: bool, source: Optional[str]) -> None:
        try:
            logger.info(
                "storage.service.initialized",
                extra={
                    "event": "storage.service.initialized",
                    "service": self.__class__.__name__,
                    "created": bool(created),
                    "source": source or "direct",
                    "is_minio": bool(self.is_minio),
                    "endpoint": self.endpoint_url or "aws-default",
                    "buckets_checked": bool(getattr(self, "_buckets_checked", False)),
                },
            )
        except Exception:
            logger.info("storage.service.initialized %s (created=%s)", self.__class__.__name__, created)

    def _maybe_warn_direct_construction(self) -> None:
        if self._current_construction_source() is not None:
            return

        cls = self.__class__
        if cls not in BaseStorageService._direct_instantiation_warnings:
            logger.warning(
                "Storage service %s instantiated without registry; use lacos.storage.services.registry helpers to ensure singleton reuse.",
                cls.__name__,
            )
            BaseStorageService._direct_instantiation_warnings.add(cls)

    @classmethod
    def _current_construction_source(cls) -> Optional[str]:
        stack = getattr(cls._construction_context, "stack", None)
        if stack:
            return stack[-1]
        return None

    def _maybe_emit_post_startup_warning(self, *, created: bool) -> None:
        cls = self.__class__
        if not created:
            return
        if not BaseStorageService._startup_complete:
            return
        if cls in BaseStorageService._post_startup_initializations:
            return

        logger.warning(
            "Storage service %s initialised after startup; consider pre-warming via storage_prefetch if this is unexpected.",
            cls.__name__,
        )
        BaseStorageService._post_startup_initializations.add(cls)

    @classmethod
    @contextmanager
    def _construction_scope(cls, source: str):
        stack = list(getattr(cls._construction_context, "stack", []))
        stack.append(source)
        cls._construction_context.stack = stack
        try:
            yield
        finally:
            stack = list(getattr(cls._construction_context, "stack", []))
            if stack:
                stack.pop()
            if stack:
                cls._construction_context.stack = stack
            elif hasattr(cls._construction_context, "stack"):
                del cls._construction_context.stack

    @classmethod
    @contextmanager
    def allow_construction(cls, source: str):
        with cls._construction_scope(source):
            yield

    @classmethod
    @contextmanager
    def allow_registry_construction(cls):
        with cls.allow_construction("registry"):
            yield

    @classmethod
    @contextmanager
    def allow_test_construction(cls):
        with cls.allow_construction("test"):
            yield

    @classmethod
    def mark_startup_complete(cls) -> None:
        cls._startup_complete = True

    @classmethod
    def reset_shared_state(cls) -> None:
        with cls._shared_runtime_lock:
            cls._shared_runtime = None
        cls._buckets_checked = False
        cls._post_startup_initializations.clear()
        cls._direct_instantiation_warnings.clear()
        cls._startup_complete = False

    @staticmethod
    def clear_service_singleton(target_cls: "BaseStorageService") -> None:
        lock = getattr(target_cls, "_instance_lock", threading.RLock())
        with lock:
            instance = getattr(target_cls, "_instance", None)
            target_cls._instance = None
        if instance and hasattr(instance, "initialized"):
            delattr(instance, "initialized")
        if hasattr(target_cls, "_buckets_checked"):
            target_cls._buckets_checked = False
    
    def set_client_and_buckets(self, service):
        """
        Ensure a child service uses the same S3 client and bucket names.
        
        Args:
            service: The child service to update
        """
        if hasattr(service, 's3_client'):
            service.s3_client = self.s3_client
            
        if hasattr(service, 'ingest_bucket'):
            service.ingest_bucket = self.ingest_bucket
            
        if hasattr(service, 'production_bucket'):
            service.production_bucket = self.production_bucket
            
        return service
    
    def _is_minio_environment(self) -> bool:
        """Determine if we're using MinIO based on settings or environment."""
        # First check for explicit setting
        use_minio = getattr(settings, 'USE_MINIO', None)
        if use_minio is not None:
            return use_minio
        
        # Then check for environment variable
        use_minio_env = os.environ.get('USE_MINIO', '').lower()
        if use_minio_env in ('true', 'yes', '1'):
            return True
        elif use_minio_env in ('false', 'no', '0'):
            return False
        
        # Finally, check if we're in a development environment
        return getattr(settings, 'DEBUG', False)
    
    def _get_endpoint_url(self) -> str:
        """Get the endpoint URL for S3/MinIO."""
        # First check for explicit setting
        endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        if endpoint_url:
            return endpoint_url
        
        # Then check for environment variable
        endpoint_url_env = os.environ.get('AWS_S3_ENDPOINT_URL', '')
        if endpoint_url_env:
            return endpoint_url_env
        
        # Default MinIO endpoint if we're using MinIO
        if self._is_minio_environment():
            return 'http://minio:9000'
        
        # For production S3, return None to use the default AWS endpoint
        return None
    
    def _get_access_key(self) -> str:
        """Get the access key for S3/MinIO."""
        # First check for explicit setting
        access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        if access_key:
            return access_key
        
        # Then check for environment variable
        access_key_env = os.environ.get('AWS_ACCESS_KEY_ID', '')
        if access_key_env:
            return access_key_env
        
        # Default MinIO access key if we're using MinIO
        if self._is_minio_environment():
            return 'minioadmin'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_ACCESS_KEY_ID found in settings or environment")
        return ''
    
    def _get_secret_key(self) -> str:
        """Get the secret key for S3/MinIO."""
        # First check for explicit setting
        secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        if secret_key:
            return secret_key
        
        # Then check for environment variable
        secret_key_env = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
        if secret_key_env:
            return secret_key_env
        
        # Default MinIO secret key if we're using MinIO
        if self._is_minio_environment():
            return 'minioadmin'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_SECRET_ACCESS_KEY found in settings or environment")
        return ''
    
    def _get_region(self) -> str:
        """Get the region for S3."""
        # First check for explicit setting
        region = getattr(settings, 'AWS_S3_REGION_NAME', None)
        if region:
            return region
        
        # Then check for environment variable
        region_env = os.environ.get('AWS_S3_REGION_NAME', '')
        if region_env:
            return region_env
        
        # Default region
        return 'us-east-1'
    
    def _get_ingest_bucket_name(self) -> Optional[str]:
        """
        Get the ingest bucket name for S3/MinIO.
        
        DEPRECATED: This is a legacy property. Use get_all_accessible_buckets() to get all buckets.
        Only returns a value if explicitly configured. Returns None otherwise.
        """
        # Check new-style setting first
        bucket_name = getattr(settings, 'S3_INGEST_BUCKET', None) or os.environ.get('S3_INGEST_BUCKET')
        if bucket_name:
            return bucket_name

        # Legacy fallback
        bucket_name = getattr(settings, 'AWS_INGEST_BUCKET_NAME', None) or os.environ.get('AWS_INGEST_BUCKET_NAME')
        if bucket_name:
            logger.debug("Using legacy AWS_INGEST_BUCKET_NAME setting")
            return bucket_name

        # Do NOT derive from workspace buckets - return None if not explicitly configured
        return None

    def _get_production_bucket_name(self) -> Optional[str]:
        """
        Get the production bucket name for S3/MinIO.
        
        DEPRECATED: This is a legacy property. Use get_all_accessible_buckets() to get all buckets.
        Only returns a value if explicitly configured. Returns None otherwise.
        """
        # Check new-style setting first
        bucket_name = getattr(settings, 'S3_PRODUCTION_BUCKET', None) or os.environ.get('S3_PRODUCTION_BUCKET')
        if bucket_name:
            return bucket_name

        # Legacy fallback
        bucket_name = getattr(settings, 'AWS_PRODUCTION_BUCKET_NAME', None) or os.environ.get('AWS_PRODUCTION_BUCKET_NAME')
        if bucket_name:
            logger.debug("Using legacy AWS_PRODUCTION_BUCKET_NAME setting")
            return bucket_name

        # Do NOT derive from workspace buckets - return None if not explicitly configured
        return None

    def _get_workspace_buckets(self) -> list:
        """Get the list of workspace buckets from settings."""
        workspace_buckets = getattr(settings, 'S3_WORKSPACE_BUCKETS', [])
        if isinstance(workspace_buckets, (list, tuple)):
            workspace_buckets = list(dict.fromkeys(str(bucket).strip() for bucket in workspace_buckets if bucket))
        elif isinstance(workspace_buckets, str):
            # Handle * or __all__ as wildcard for all buckets
            workspace_buckets_str = workspace_buckets.strip()
            if workspace_buckets_str in ("*", "__all__", ""):
                workspace_buckets = ["*"]  # Use * as marker for "all buckets"
            else:
                # Split comma-separated list
                workspace_buckets = [b.strip() for b in workspace_buckets_str.split(",") if b.strip()]
        else:
            workspace_buckets = []

        logger.info("Loaded workspace buckets from settings: %s", workspace_buckets)
        return workspace_buckets

    @property
    def ocfl_buckets(self) -> list:
        """
        Get all accessible buckets as OCFL-capable buckets.
        
        Note: This property triggers lazy loading when first accessed.
        All buckets are OCFL-capable.
        """
        return self.get_all_accessible_buckets()

    def is_ocfl_bucket(self, bucket_name: str) -> bool:
        """Check if a bucket allows OCFL operations. All buckets are OCFL-capable."""
        return True

    def _lazy_fetch_buckets(self) -> Generator[str, None, None]:
        """
        Lazy generator that yields buckets one at a time.
        Only fetches from S3 when iterated, not on call.
        
        Returns:
            Generator[str, None, None]: Lazy iterator yielding bucket names
        """
        # Check if we should allow all buckets
        allow_all = any(bucket in ("*", "__all__") for bucket in self.workspace_buckets)
        allow_all = allow_all or not self.workspace_buckets  # Empty list also means all buckets

        if not allow_all:
            # If specific buckets are configured, yield only those (no S3 call needed)
            allowlist = [bucket for bucket in self.workspace_buckets if bucket not in ("*", "__all__")]
            allowlist = list(dict.fromkeys(allowlist))
            
            if allowlist and not self.is_minio:
                # For external S3 with allowlist, verify buckets exist as we yield them
                for bucket_name in allowlist:
                    try:
                        # Lazy check: only verify bucket exists when yielding
                        self.s3_client.head_bucket(Bucket=bucket_name)
                        yield bucket_name
                    except ClientError:
                        logger.debug("Bucket '%s' not accessible, skipping", bucket_name)
                return
            elif allowlist:
                # For MinIO with allowlist, just yield them
                yield from allowlist
                return

        # For "all buckets" mode, fetch lazily from S3
        try:
            response = self.s3_client.list_buckets()
            all_bucket_names = sorted(bucket['Name'] for bucket in response['Buckets'])
            logger.debug("📦 BUCKETS: Lazy fetch found %s buckets", len(all_bucket_names))
            
            for bucket_name in all_bucket_names:
                yield bucket_name
        except Exception as e:
            logger.exception("❌ Error listing buckets lazily: %s", e)
            # Fallback: yield workspace buckets if configured
            if self.workspace_buckets and self.workspace_buckets != ["*"]:
                for b in self.workspace_buckets:
                    if b not in ("*", "__all__"):
                        yield b

    def get_all_accessible_buckets(self, force_refresh: bool = False, raise_on_error: bool = False) -> list:
        """
        Get all accessible buckets dynamically from S3/MinIO.
        
        This method uses lazy loading - buckets are only fetched when this method is called,
        not during service initialization. Use iter_buckets() for true lazy iteration.
        
        Args:
            force_refresh (bool): If True, bypass the in-memory cache and fetch fresh data.
            raise_on_error (bool): If True, propagate underlying S3 errors instead of returning fallbacks.

        Returns:
            list: List of accessible bucket names
        """
        cache_key = self._bucket_cache_key()

        if force_refresh:
            cache.delete(cache_key)

        cached = cache.get(cache_key)
        if cached is not None:
            expires_in = None
            ttl_fn = getattr(cache, "ttl", None)
            if callable(ttl_fn):
                try:
                    expires_in = ttl_fn(cache_key)
                except Exception:  # pragma: no cover - backend without ttl support
                    expires_in = None
            self._bucket_cache_metadata = {
                "source": "cache",
                "bucket_count": len(cached),
                "expires_in": expires_in,
                "duration": 0.0,
                "force_refresh": force_refresh,
            }
            self._update_shared_runtime("bucket_cache_metadata", self._bucket_cache_metadata)
            logger.info(
                "storage.bucket_cache",
                extra={
                    "event": "storage.bucket_cache",
                    "action": "hit",
                    "bucket_count": len(cached),
                    "expires_in": expires_in,
                    "force_refresh": force_refresh,
                },
            )
            logger.debug("Returning cached bucket list (%d buckets)", len(cached))
            return list(cached)

        try:
            fetch_start = time.monotonic()
            bucket_names = list(self._lazy_fetch_buckets())
            fetch_duration = time.monotonic() - fetch_start
            
            # Check if we should allow all buckets (for logging)
            allow_all = any(bucket in ("*", "__all__") for bucket in self.workspace_buckets)
            allow_all = allow_all or not self.workspace_buckets
            
            if allow_all:
                logger.info("📦 BUCKETS: All buckets mode enabled, found %s buckets", len(bucket_names))
            else:
                logger.info("📦 BUCKETS: Found %s accessible buckets (filtered)", len(bucket_names))

            ttl_seconds = self._bucket_cache_ttl()
            self._bucket_cache_metadata = {
                "source": "refresh",
                "bucket_count": len(bucket_names),
                "duration": fetch_duration,
                "expires_in": ttl_seconds,
                "force_refresh": force_refresh,
            }
            self._update_shared_runtime("bucket_cache_metadata", self._bucket_cache_metadata)
            logger.info(
                "storage.bucket_cache",
                extra={
                    "event": "storage.bucket_cache",
                    "action": "refresh",
                    "bucket_count": len(bucket_names),
                    "duration": fetch_duration,
                    "ttl": ttl_seconds,
                    "force_refresh": force_refresh,
                },
            )
            cache.set(cache_key, bucket_names, timeout=ttl_seconds)

            return bucket_names
        except Exception as e:
            logger.exception("❌ Error getting buckets: %s", e)
            cache.delete(cache_key)

            if raise_on_error:
                raise

            self._bucket_cache_metadata = {
                "source": "fallback",
                "error": str(e),
                "force_refresh": force_refresh,
            }
            self._update_shared_runtime("bucket_cache_metadata", self._bucket_cache_metadata)
            logger.warning(
                "storage.bucket_cache",
                extra={
                    "event": "storage.bucket_cache",
                    "action": "fallback",
                    "error": str(e),
                    "force_refresh": force_refresh,
                },
            )
            # Fallback: return workspace buckets if configured, otherwise empty list
            if self.workspace_buckets and self.workspace_buckets != ["*"]:
                return [b for b in self.workspace_buckets if b not in ("*", "__all__")]
            return []

    def iter_buckets(self) -> Generator[str, None, None]:
        """
        Return a lazy iterator over accessible buckets.
        Buckets are fetched from S3 only when iterated, not on call.
        
        Use this when you only need to iterate through buckets and don't need a list.
        
        Example:
            for bucket in service.iter_buckets():
                process(bucket)
        
        Returns:
            Generator[str, None, None]: Lazy iterator yielding bucket names
        """
        return self._lazy_fetch_buckets()

    def _create_s3_client(self):
        """
        Create an S3 client configured for the current environment.
        
        Returns:
            boto3.client: Configured S3 client
        """
        # Basic client configuration
        client_kwargs = {
            'service_name': 's3',
            'aws_access_key_id': self.access_key,
            'aws_secret_access_key': self.secret_key,
        }
        
        # Add region if specified
        if self.region:
            client_kwargs['region_name'] = self.region
        
        # Add endpoint URL for MinIO or custom S3 endpoints
        if self.endpoint_url:
            # For server-side operations, use the original endpoint URL
            server_endpoint = self.endpoint_url
            client_kwargs['endpoint_url'] = server_endpoint

            # For any custom endpoint (MinIO or S3-compatible), use path-style addressing
            # This prevents boto3 from trying virtual-hosted-style URLs like https://bucket.endpoint.com
            client_kwargs['config'] = boto3.session.Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            )

            # For MinIO in local development, we need special handling for presigned URLs
            if self.is_minio:
                # Create a config that tells boto3 to use path-style addressing
                # This is required for MinIO
                client_kwargs['config'] = boto3.session.Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'}
                )
                
                # For presigned URLs that will be used by the browser,
                # we need to use a browser-accessible URL
                browser_endpoint = os.environ.get('AWS_S3_BROWSER_ENDPOINT_URL', None)
                
                if browser_endpoint:
                    logger.info(f"Using browser endpoint URL from environment: {browser_endpoint}")
                elif 'minio:9000' in self.endpoint_url:
                    # Default fallback for local development
                    browser_endpoint = self.endpoint_url.replace('minio:9000', 'localhost:9000')
                    logger.info(f"MinIO detected at {self.endpoint_url}, will use {browser_endpoint} for presigned URLs")
                else:
                    # If no specific browser endpoint is provided, use the same as server
                    browser_endpoint = self.endpoint_url
                    logger.info(f"Using server endpoint for presigned URLs: {browser_endpoint}")
                
                # Create a separate client for generating presigned URLs
                self.presigned_client = boto3.client(
                    's3',
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region if self.region else None,
                    endpoint_url=browser_endpoint,
                    config=boto3.session.Config(
                        signature_version='s3v4',
                        s3={'addressing_style': 'path'}
                    )
                )
                logger.info(f"Created separate client for presigned URLs with endpoint: {browser_endpoint}")
        
        # Create the primary client
        client = boto3.client(**client_kwargs)

        # Ensure a presigned client always exists; fall back to the primary client
        if not hasattr(self, "presigned_client"):
            self.presigned_client = client

        return client
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """
        Ensure that the specified bucket exists, creating it if necessary.
        
        Args:
            bucket_name (str): The name of the bucket to check/create.
            
        Returns:
            bool: True if the bucket exists or was created successfully, False otherwise.
        """
        logger.info(f"Checking if bucket '{bucket_name}' exists...")
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"✅ Bucket '{bucket_name}' already exists")
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.info(f"Bucket check result: {error_code} - {error_message}")
            
            # If bucket doesn't exist, create it
            if error_code == '404' or error_code == 'NoSuchBucket':
                try:
                    logger.info(f"🔄 Creating bucket '{bucket_name}' in region '{self.region}'...")
                    if self.region == 'us-east-1':
                        # Special case for us-east-1
                        logger.info(f"Using special case for us-east-1 region (no LocationConstraint)")
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        logger.info(f"Using LocationConstraint={self.region}")
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info(f"✅ Bucket '{bucket_name}' created successfully")
                    return True
                except Exception as create_error:
                    logger.error(f"❌ Error creating bucket '{bucket_name}': {str(create_error)}")
                    # Log more details about the error
                    if hasattr(create_error, 'response'):
                        error_details = create_error.response.get('Error', {})
                        logger.error(f"Error details: Code={error_details.get('Code')}, Message={error_details.get('Message')}")
                    return False
            else:
                logger.error(f"❌ Error checking bucket '{bucket_name}': {error_code} - {error_message}")
                return False
    
    def get_file_content(self, bucket_name: str, file_path: str) -> Dict[str, Any]:
        """
        Get the content of a file from the specified bucket.
        
        Args:
            bucket_name (str): The name of the bucket containing the file
            file_path (str): The path to the file in the bucket
            
        Returns:
            Dict[str, Any]: A dictionary containing the file content and metadata
        """
        try:
            response = self.s3_client.get_object(
                Bucket=bucket_name, Key=file_path
            )
            
            # Get the file content
            content = response["Body"].read()
            
            # Get the file metadata
            metadata = {
                "content_type": response.get("ContentType", "application/octet-stream"),
                "content_length": response.get("ContentLength", 0),
                "last_modified": response.get("LastModified", None),
            }
            
            return {
                "content": content,
                "metadata": metadata,
                "bucket_name": bucket_name,
                "path": file_path,
            }
        except ClientError as e:
            logger.error(f"Error getting file content for {file_path}: {str(e)}")
            return {"error": str(e)}
            
    def delete_object(self, bucket_name: str, object_path: str, is_directory: bool = False) -> Dict[str, Any]:
        """
        Delete an object or directory from the specified bucket.
        
        Args:
            bucket_name (str): The name of the bucket containing the object
            object_path (str): The path to the object in the bucket
            is_directory (bool, optional): Whether the object is a directory. Defaults to False.
            
        Returns:
            Dict[str, Any]: A dictionary containing the result of the operation
        """
        try:
            if is_directory:
                # For directories, we need to delete all objects with the given prefix
                paginator = self.s3_client.get_paginator("list_objects_v2")
                
                objects_to_delete = []
                for page in paginator.paginate(Bucket=bucket_name, Prefix=object_path):
                    for obj in page.get("Contents", []):
                        objects_to_delete.append({"Key": obj["Key"]})
                
                if objects_to_delete:
                    # Some S3-compatible services (like MinIO) require Content-MD5 for DeleteObjects
                    # We'll delete each object individually to avoid this issue
                    logger.info(f"Deleting {len(objects_to_delete)} objects from {bucket_name}/{object_path}")
                    deleted_count = 0
                    for obj in objects_to_delete:
                        try:
                            self.s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                            deleted_count += 1
                        except Exception as obj_error:
                            logger.error(f"Error deleting object {obj['Key']}: {str(obj_error)}")
                    
                    return {
                        "success": deleted_count > 0,
                        "message": f"Successfully deleted directory {object_path} with {deleted_count} objects",
                        "deleted_objects": deleted_count
                    }
                else:
                    return {
                        "success": True,
                        "message": f"Directory {object_path} was empty, nothing to delete",
                        "deleted_objects": 0
                    }
            else:
                # For single objects, just delete the object
                self.s3_client.delete_object(Bucket=bucket_name, Key=object_path)
                
                return {
                    "success": True,
                    "message": f"Successfully deleted object {object_path}",
                    "deleted_objects": 1
                }
        except ClientError as e:
            logger.error(f"Error deleting {object_path}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def ensure_cors_enabled(self, bucket_name: str) -> Dict[str, Any]:
        """
        Ensure CORS is properly configured for the specified bucket.
        
        This is required for browser-based uploads to work properly.
        
        Args:
            bucket_name (str): Name of the bucket to configure.
        
        Returns:
            Dict[str, Any]: Result of the operation
        """
        if not bucket_name:
            return {"success": False, "error": "Bucket name is required"}
        
        logger.info(f"Checking CORS configuration for bucket: {bucket_name}")
        
        try:
            # Define the required CORS rule - using the exact minimal configuration provided
            required_rule = {
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['POST'],
                'AllowedOrigins': ['*'],
                'ExposeHeaders': []
            }
            
            # Check if CORS is already configured
            try:
                cors_config = self.s3_client.get_bucket_cors(Bucket=bucket_name)
                current_rules = cors_config.get('CORSRules', [])
                logger.info(f"Found existing CORS configuration with {len(current_rules)} rules")
                
                # Check if our required rule already exists
                rule_exists = False
                for rule in current_rules:
                    # Check if all required keys are in the existing rule
                    if (set(rule.get('AllowedHeaders', [])) >= set(required_rule['AllowedHeaders']) and
                        set(rule.get('AllowedMethods', [])) >= set(required_rule['AllowedMethods']) and
                        set(rule.get('AllowedOrigins', [])) >= set(required_rule['AllowedOrigins'])):
                        rule_exists = True
                        logger.info("✅ Required CORS rule already exists")
                        break
                
                # If the rule doesn't exist, add it
                if not rule_exists:
                    logger.info("🔄 Required CORS rule not found, updating configuration...")
                    
                    # Use existing rules if any, otherwise create a new configuration
                    new_rules = current_rules.copy() if current_rules else []
                    new_rules.append(required_rule)
                    
                    # Apply the updated CORS configuration
                    self.s3_client.put_bucket_cors(
                        Bucket=bucket_name,
                        CORSConfiguration={'CORSRules': new_rules}
                    )
                    logger.info("✅ CORS configuration updated successfully")
                    return {"success": True, "message": "CORS configuration updated", "updated": True}
                
                return {"success": True, "message": "CORS already properly configured", "updated": False}
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                
                # If no CORS configuration exists, create one
                if error_code == 'NoSuchCORSConfiguration':
                    logger.info("No existing CORS configuration found, creating new configuration...")
                    
                    # Create a new CORS configuration with our required rule
                    self.s3_client.put_bucket_cors(
                        Bucket=bucket_name,
                        CORSConfiguration={'CORSRules': [required_rule]}
                    )
                    logger.info("✅ CORS configuration created successfully")
                    return {"success": True, "message": "CORS configuration created", "updated": True}
                else:
                    # Some other error occurred
                    logger.error(f"❌ Error getting CORS configuration: {error_code} - {error_message}")
                    return {"success": False, "error": f"{error_code}: {error_message}"}
        
        except Exception as e:
            logger.error(f"❌ Error ensuring CORS configuration: {str(e)}")
            
            # For MinIO, CORS might not be fully supported, but uploads might still work
            if self.is_minio:
                logger.warning("⚠️ CORS configuration failed, but this is expected with some MinIO versions")
                logger.warning("⚠️ Browser uploads may still work despite this error")
                return {"success": True, "message": "CORS configuration skipped for MinIO", "updated": False}
            
            return {"success": False, "error": str(e)}

    def _is_running_in_container(self):
        """
        Determine if we're running inside a Docker container.
        
        Returns:
            bool: True if running in a container, False otherwise
        """
        # Check for the RUNNING_IN_CONTAINER environment variable
        if os.environ.get('RUNNING_IN_CONTAINER'):
            return True
        
        # Check for .dockerenv file
        if os.path.exists('/.dockerenv'):
            return True
        
        # Check cgroup
        try:
            with open('/proc/1/cgroup', 'r') as f:
                return 'docker' in f.read() or 'kubepods' in f.read()
        except:
            pass
        
        return False 
    def _bucket_cache_key(self) -> str:
        return "storage:bucket-names"

    def _bucket_cache_ttl(self) -> int:
        """Return the configured bucket list cache TTL in seconds."""
        ttl = getattr(settings, "S3_BUCKET_LIST_CACHE_TTL", 300)
        try:
            ttl_int = int(ttl)
        except (TypeError, ValueError):
            ttl_int = 300
        return max(ttl_int, 1)

    def invalidate_bucket_cache(self) -> None:
        """Clear the cached bucket list."""
        cache.delete(self._bucket_cache_key())
        self._bucket_cache_metadata = {}
        self._update_shared_runtime("bucket_cache_metadata", self._bucket_cache_metadata)

    @property
    def bucket_cache_metadata(self) -> Dict[str, Any]:
        """Return metadata about the most recent bucket cache population."""
        return getattr(self, "_bucket_cache_metadata", {})
