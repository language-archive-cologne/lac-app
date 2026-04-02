# ruff: noqa: ERA001, E501
"""Base settings to build other settings files upon."""


from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# lacos/
APPS_DIR = BASE_DIR / "lacos"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

SAML_LOGIN_ENABLED = env.bool("SAML_LOGIN_ENABLED", default=False)

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
# from django.utils.translation import gettext_lazy as _
# LANGUAGES = [
#     ('en', _('English')),
#     ('fr-fr', _('French')),
#     ('pt-br', _('Portuguese')),
# ]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.admin",
    "django.contrib.postgres",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.socialaccount",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "huey.contrib.djhuey",
    "django_filters",
]
if SAML_LOGIN_ENABLED:
    THIRD_PARTY_APPS.append("djangosaml2")

LOCAL_APPS = [
    "lacos.users",
    "lacos.common",  # Common utilities and mixins
    "lacos.cache",
    "lacos.blam",
    "lacos.storage",
    "lacos.oaipmh",
    "lacos.rest",
    "lacos.ingest",
    "lacos.explorer",
    "lacos.dbadmin",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "lacos.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
if SAML_LOGIN_ENABLED:
    AUTHENTICATION_BACKENDS.append("lacos.users.backends.LacosSaml2Backend")
AUTHENTICATION_BACKENDS.append("allauth.account.auth_backends.AuthenticationBackend")
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

if SAML_LOGIN_ENABLED:
    session_middleware = "django.contrib.sessions.middleware.SessionMiddleware"
    try:
        session_index = MIDDLEWARE.index(session_middleware)
    except ValueError:
        session_index = 0
    MIDDLEWARE.insert(
        session_index + 1,
        "djangosaml2.middleware.SamlSessionMiddleware",
    )

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [
    str(APPS_DIR / "static"),
    str(BASE_DIR / "theme" / "static"),
]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# GUIDELINES
# ------------------------------------------------------------------------------
GUIDELINES_REPO_URL = env(
    "GUIDELINES_REPO_URL",
    default="https://gitlab.git.nrw/uzk-lac/lac-guidelines.git",
)
GUIDELINES_HTML_DIR = Path(MEDIA_ROOT) / "guidelines"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "lacos.users.context_processors.allauth_settings",
                "lacos.users.context_processors.version_info",
                "lacos.storage.context_processors.upload_client_config",
            ],
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("""Francisco Mondaca""", "mondaca@uni-koeln.de")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# https://cookiecutter-django.readthedocs.io/en/latest/settings.html#other-environment-settings
# Force the `admin` sign in process to go through the `django-allauth` workflow
DJANGO_ADMIN_FORCE_ALLAUTH = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")
REDIS_SSL = REDIS_URL.startswith("rediss://")
HUEY_IMMEDIATE = env.bool("HUEY_IMMEDIATE", default=DEBUG)
HUEY_WORKERS = env.int("HUEY_WORKERS", default=2)

# Huey (Task Queue) Configuration
# ------------------------------------------------------------------------------
HUEY = {
    'huey_class': 'huey.RedisHuey',
    'name': 'lacos',
    'results': True,
    'store_none': False,
    'immediate': HUEY_IMMEDIATE,
    'utc': True,
    'blocking': True,
    'connection': {
        'url': REDIS_URL,
    },
    'consumer': {
        'workers': HUEY_WORKERS,
        'worker_type': 'thread',
        'initial_delay': 0.1,  # Smallest polling interval
        'backoff': 1.15,  # Exponential backoff rate
        'max_delay': 10.0,  # Max polling interval
        'scheduler_interval': 1,  # Check schedule every second
        'periodic': True,  # Enable crontab feature
        'check_worker_health': True,  # Enable worker health checks
        'health_check_interval': 1,  # Check worker health every second
    },
}

# Collection Path Structure Configuration
# ------------------------------------------------------------------------------
# Path patterns for collections, bundles, and resources
COLLECTION_PATH_PATTERN = env("COLLECTION_PATH_PATTERN")
BUNDLE_PATH_PATTERN = env("BUNDLE_PATH_PATTERN")
RESOURCE_PATH_PATTERN = env("RESOURCE_PATH_PATTERN")

# Explorer Map Configuration
# ------------------------------------------------------------------------------
EXPLORER_MAIN_MAP_STYLE_URL = env(
    "EXPLORER_MAIN_MAP_STYLE_URL",
    default="/static/vendor/maps/openfreemap/bright.json",
)
EXPLORER_MAIN_MAP_DARK_STYLE_URL = env(
    "EXPLORER_MAIN_MAP_DARK_STYLE_URL",
    default=EXPLORER_MAIN_MAP_STYLE_URL,
)

# Storage Configuration
# ------------------------------------------------------------------------------
# S3/MinIO bucket configuration for flexible workspace access
# Default workspace buckets - use actual bucket names, can be overridden by environment variables
S3_WORKSPACE_BUCKETS = env.list("S3_WORKSPACE_BUCKETS", default=["lacos-ingest", "lacos-production"])

# Buckets where OCFL operations are allowed (subset of workspace buckets)
S3_OCFL_BUCKETS = env.list("S3_OCFL_BUCKETS", default=["lacos-ingest", "lacos-production"])

# Legacy bucket names for backward compatibility
# These map to the actual bucket names used by the legacy configuration
S3_INGEST_BUCKET = env("S3_INGEST_BUCKET", default="lacos-ingest")
S3_PRODUCTION_BUCKET = env("S3_PRODUCTION_BUCKET", default="lacos-production")
# Increase botocore HTTP pool size to avoid connection pool saturation under Huey/media load.
AWS_S3_MAX_POOL_CONNECTIONS = env.int("AWS_S3_MAX_POOL_CONNECTIONS", default=50)

# Cache configuration for storage subsystems
STORAGE_ACL_CACHE_TIMEOUT = env.int("STORAGE_ACL_CACHE_TIMEOUT", default=900)
# Dashboard listing pagination (used by archivist/storage folder browsing)
STORAGE_DASHBOARD_PAGINATION_ENABLED = env.bool(
    "STORAGE_DASHBOARD_PAGINATION_ENABLED",
    default=True,
)
STORAGE_DASHBOARD_PAGE_SIZE = env.int("STORAGE_DASHBOARD_PAGE_SIZE", default=200)

# Presigned URL Configuration
# ------------------------------------------------------------------------------
# Default expiration time for presigned download URLs (in seconds)
# 86400 = 24 hours - allows resumable downloads for large files
PRESIGNED_URL_EXPIRATION = env.int("PRESIGNED_URL_EXPIRATION", default=86400)
# Buffer time to subtract from expiration when caching URLs (handles clock skew)
PRESIGNED_URL_CACHE_BUFFER = env.int("PRESIGNED_URL_CACHE_BUFFER", default=300)
# Require S3ResourceLocation record to exist for download authorization
# When True (default), only resources tracked in the database can be downloaded
# Set to False to allow downloads of unmapped resources (INSECURE - use with caution)
REQUIRE_S3_LOCATION_FOR_DOWNLOAD = env.bool("REQUIRE_S3_LOCATION_FOR_DOWNLOAD", default=True)

# ALTCHA Configuration (Proof-of-Work bot protection)
# ------------------------------------------------------------------------------
# Secret key for HMAC signing challenges (defaults to SECRET_KEY if not set)
ALTCHA_HMAC_KEY = env("ALTCHA_HMAC_KEY", default=None)
# Difficulty level: higher = more computation (50000 ~ 1-2 seconds)
ALTCHA_MAX_NUMBER = env.int("ALTCHA_MAX_NUMBER", default=50000)
# Challenge expiration in seconds
ALTCHA_EXPIRES_SECONDS = env.int("ALTCHA_EXPIRES_SECONDS", default=300)

# ACL Configuration
# ------------------------------------------------------------------------------
ACL_ENFORCEMENT_ENABLED = env.bool("ACL_ENFORCEMENT_ENABLED", default=True)
ACL_LOG_ACCESS_ATTEMPTS = env.bool("ACL_LOG_ACCESS_ATTEMPTS", default=True)
ACL_DEFAULT_DENY = env.bool("ACL_DEFAULT_DENY", default=True)
ACL_SYNC_ON_STARTUP = env.bool("ACL_SYNC_ON_STARTUP", default=False)

# Multipart Upload Configuration
# ------------------------------------------------------------------------------
MULTIPART_UPLOAD_SETTINGS = {
    # File size thresholds - default keeps single uploads up to 5GB (S3 limit)
    'multipart_threshold': env.int('MULTIPART_THRESHOLD', default=100 * 1024 * 1024),
    'resumable_threshold': env.int('RESUMABLE_THRESHOLD', default=5 * 1024 * 1024 * 1024),

    # Chunk sizing (100MB chunks balance request count vs throughput)
    'chunk_size': env.int('MULTIPART_CHUNK_SIZE', default=100 * 1024 * 1024),
    'resumable_chunk_size': env.int('RESUMABLE_CHUNK_SIZE', default=100 * 1024 * 1024),
    'min_part_size': env.int('MULTIPART_MIN_PART_SIZE', default=5 * 1024 * 1024),
    'max_parts': env.int('MULTIPART_MAX_PARTS', default=10000),

    # Concurrency tuning
    'max_workers': env.int('MULTIPART_MAX_WORKERS', default=12),
    'max_concurrency': env.int('MULTIPART_MAX_CONCURRENCY', default=8),
    'part_upload_concurrency': env.int('MULTIPART_PART_UPLOAD_CONCURRENCY', default=6),

    # Retry/timeout behaviour
    'max_retries': env.int('MULTIPART_MAX_RETRIES', default=3),
    'retry_delay_base': env.float('MULTIPART_RETRY_DELAY_BASE', default=0.5),
    'retry_max_delay': env.int('MULTIPART_RETRY_MAX_DELAY', default=30),
    'chunk_timeout': env.int('MULTIPART_CHUNK_TIMEOUT', default=300),
    'total_timeout': env.int('MULTIPART_TOTAL_TIMEOUT', default=3600),

    # Operational toggles
    'enable_resume': env.bool('MULTIPART_ENABLE_RESUME', default=True),
    'cleanup_failed_uploads': env.bool('MULTIPART_CLEANUP_FAILED', default=True),
}

# Upload Verification Configuration
# ------------------------------------------------------------------------------
# Grace period before background verification runs on in-progress sessions.
UPLOAD_VERIFICATION_GRACE_SECONDS = env.int(
    "UPLOAD_VERIFICATION_GRACE_SECONDS",
    default=24 * 60 * 60,
)
# Periodic schedule interval for verification tasks (minutes).
UPLOAD_VERIFICATION_SCHEDULE_MINUTES = env.int(
    "UPLOAD_VERIFICATION_SCHEDULE_MINUTES",
    default=15,
)

# Database backup configuration
# ------------------------------------------------------------------------------
DB_BACKUP_ENABLED = env.bool("DB_BACKUP_ENABLED", default=False)
DB_BACKUP_COMPOSE_FILE = env("DB_BACKUP_COMPOSE_FILE", default="docker-compose.dev.yml")
DB_BACKUP_COMPOSE_PROJECT_DIR = env("DB_BACKUP_COMPOSE_PROJECT_DIR", default=str(BASE_DIR))
DB_BACKUP_COMPOSE_PROJECT_NAME = env("DB_BACKUP_COMPOSE_PROJECT_NAME", default="")
DB_BACKUP_BACKUP_DIR = env("DB_BACKUP_BACKUP_DIR", default="/backups")
DB_BACKUP_S3_BUCKET = env("DB_BACKUP_S3_BUCKET", default="backups")
DB_BACKUP_S3_PREFIX = env("DB_BACKUP_S3_PREFIX", default="db-backups")
DB_BACKUP_RETENTION_DAYS = env.int("DB_BACKUP_RETENTION_DAYS", default=7)
DB_BACKUP_CRON_HOUR = env.int("DB_BACKUP_CRON_HOUR", default=2)
DB_BACKUP_CRON_MINUTE = env.int("DB_BACKUP_CRON_MINUTE", default=0)

# django-allauth
# ------------------------------------------------------------------------------
ACCOUNT_ALLOW_REGISTRATION = False
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_LOGIN_METHODS = {"username"}
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_EMAIL_REQUIRED = True
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_EMAIL_VERIFICATION = "none"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER = "lacos.users.adapters.AccountAdapter"
# https://docs.allauth.org/en/latest/account/forms.html
ACCOUNT_FORMS = {"signup": "lacos.users.forms.UserSignupForm"}
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER = "lacos.users.adapters.SocialAccountAdapter"
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_FORMS = {"signup": "lacos.users.forms.UserSocialSignupForm"}

# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "300/minute",
        "auth": "10/minute",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_ALL_ORIGINS = True

SPECTACULAR_SETTINGS = {
    "TITLE": "Language Archive Cologne API",
    "DESCRIPTION": (
        "BLAM (Basic Language Archive Metadata) API for the Language Archive Cologne.\n\n"
        "Public records are available without authentication. "
        "Restricted records require a JWT token.\n\n"
        "## Getting a token\n\n"
        "**Service accounts:** `POST /auth/token/` with username and password.\n\n"
        "**University users (Shibboleth):** Log in at `/saml2/login/`, "
        "then use the `/auth/session-token/` endpoint below (Try it out) to "
        "exchange your session for a JWT. Copy the token from the response. "
        "There is no programmatic Shibboleth flow.\n\n"
        "Include the token as `Authorization: Bearer <token>`. "
        "Tokens expire after 1 hour — use `/auth/token/refresh/` to renew."
    ),
    "VERSION": "2.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SCHEMA_PATH_PREFIX": "/api/v2/",
    "PREPROCESSING_HOOKS": ["lacos.rest.v2.schema.filter_v2_endpoints"],
}

# SAML metadata refresh
# ------------------------------------------------------------------------------
SAML_METADATA_REFRESH_ENABLED = env.bool(
    "SAML_METADATA_REFRESH_ENABLED",
    default=SAML_LOGIN_ENABLED,
)
SAML_METADATA_REFRESH_URL = env(
    "SAML_METADATA_REFRESH_URL",
    default="https://idp.rrz.uni-koeln.de/idp/shibboleth",
)
SAML_METADATA_REFRESH_PATH = env("SAML_METADATA_REFRESH_PATH", default="")
SAML_METADATA_REFRESH_TIMEOUT_SECONDS = env.int(
    "SAML_METADATA_REFRESH_TIMEOUT_SECONDS",
    default=15,
)
SAML_METADATA_REFRESH_CRON_HOUR = env.int(
    "SAML_METADATA_REFRESH_CRON_HOUR",
    default=3,
)
SAML_METADATA_REFRESH_CRON_MINUTE = env.int(
    "SAML_METADATA_REFRESH_CRON_MINUTE",
    default=5,
)
SAML_METADATA_REFRESH_EXPECTED_ENTITY_ID = env(
    "SAML_METADATA_REFRESH_EXPECTED_ENTITY_ID",
    default="",
)

# SAML / Shibboleth
# ------------------------------------------------------------------------------
if SAML_LOGIN_ENABLED:
    from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT  # type: ignore[import-not-found]

    SAML_SP_BASE_URL = env("SAML_SP_BASE_URL", default="http://localhost:8000")
    _saml_base = SAML_SP_BASE_URL.rstrip("/")
    SAML_ENTITY_ID = env("SAML_ENTITY_ID", default=f"{_saml_base}/saml2/metadata/")
    SAML_ASSERTION_CONSUMER_SERVICE_URL = env(
        "SAML_ASSERTION_CONSUMER_SERVICE_URL",
        default=f"{_saml_base}/saml2/acs/",
    )
    SAML_SINGLE_LOGOUT_SERVICE_URL = env(
        "SAML_SINGLE_LOGOUT_SERVICE_URL",
        default=f"{_saml_base}/saml2/ls/",
    )
    SAML_DEFAULT_NAME_ID_FORMAT = env(
        "SAML_NAME_ID_FORMAT",
        default="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
    )
    SAML_USE_NAME_ID_AS_USERNAME = env.bool(
        "SAML_USE_NAME_ID_AS_USERNAME",
        default=False,
    )
    SAML_DJANGO_USER_MAIN_ATTRIBUTE = env(
        "SAML_DJANGO_USER_MAIN_ATTRIBUTE",
        default="username",
    )
    SAML_METADATA_LOCAL = env.list(
        "SAML_IDP_METADATA_LOCAL",
        default=[str(BASE_DIR / "shibboleth.xml")],
    )
    SAML_METADATA_REMOTE = [
        {"url": url}
        for url in env.list("SAML_IDP_METADATA_REMOTE", default=[])
    ]
    _saml_metadata_mdq_url = env("SAML_METADATA_MDQ_URL", default="")
    SAML2_DISCO_URL = env("SAML2_DISCO_URL", default="")
    EDUGAIN_METADATA_URL = env(
        "EDUGAIN_METADATA_URL",
        default="https://www.aai.dfn.de/fileadmin/metadata/dfn-aai-edugain+idp-metadata.xml",
    )
    SAML_ATTRIBUTE_MAPPING = {
        "eduPersonPrincipalName": ("username",),
        "urn:oid:1.3.6.1.4.1.5923.1.1.1.6": ("username",),
    }
    _saml_metadata: dict[str, list] = {}
    if SAML_METADATA_LOCAL:
        _saml_metadata["local"] = SAML_METADATA_LOCAL
    if SAML_METADATA_REMOTE:
        _saml_metadata["remote"] = SAML_METADATA_REMOTE
    if _saml_metadata_mdq_url:
        _saml_metadata["mdq"] = [{"url": _saml_metadata_mdq_url}]
    if not _saml_metadata:
        _saml_metadata["local"] = [str(BASE_DIR / "shibboleth.xml")]
    SAML_CONFIG = {
        "debug": DEBUG,
        "entityid": SAML_ENTITY_ID,
        "name": "Language Archive Cologne",
        "allow_unknown_attributes": True,
        "service": {
            "sp": {
                "name": "Language Archive Cologne",
                "endpoints": {
                    "assertion_consumer_service": [
                        (SAML_ASSERTION_CONSUMER_SERVICE_URL, BINDING_HTTP_POST),
                    ],
                    "single_logout_service": [
                        (SAML_SINGLE_LOGOUT_SERVICE_URL, BINDING_HTTP_REDIRECT),
                    ],
                },
                "allow_unsolicited": env.bool(
                    "SAML_ALLOW_UNSOLICITED",
                    default=True,
                ),
                "authn_requests_signed": env.bool(
                    "SAML_AUTHN_REQUESTS_SIGNED",
                    default=False,
                ),
                "logout_requests_signed": env.bool(
                    "SAML_LOGOUT_REQUESTS_SIGNED",
                    default=False,
                ),
                "want_assertions_signed": env.bool(
                    "SAML_WANT_ASSERTIONS_SIGNED",
                    default=True,
                ),
                "want_response_signed": env.bool(
                    "SAML_WANT_RESPONSE_SIGNED",
                    default=False,
                ),
                "name_id_format": [SAML_DEFAULT_NAME_ID_FORMAT],
                "required_attributes": ["eduPersonPrincipalName"],
            },
        },
        "http_client_timeout": env.int("SAML_HTTP_CLIENT_TIMEOUT", default=10),
        "metadata": _saml_metadata,
        "organization": {
            "name": [("University of Cologne", "en")],
            "display_name": [("University of Cologne", "en")],
            "url": [("https://www.uni-koeln.de/", "en")],
        },
        "contact_person": [
            {
                "contact_type": "technical",
                "given_name": "Francisco",
                "sur_name": "Mondaca",
                "email_address": ["mailto:mondaca@uni-koeln.de"],
            },
            {
                "contact_type": "support",
                "email_address": ["mailto:lac-helpdesk@uni-koeln.de"],
            },
        ],
        "security": {
            "wantAttributeStatementSigned": True,
            "requestedAuthnContext": env.list(
                "SAML_REQUESTED_AUTHN_CONTEXT",
                default=[
                    "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport",
                ],
            ),
        },
    }
    _saml_key_file = env("SAML_SP_KEY_FILE", default="")
    if _saml_key_file:
        SAML_CONFIG["key_file"] = _saml_key_file
    _saml_cert_file = env("SAML_SP_CERT_FILE", default="")
    if _saml_cert_file:
        SAML_CONFIG["cert_file"] = _saml_cert_file
    _saml_xmlsec = env("SAML_XMLSEC_BINARY", default="/usr/bin/xmlsec1")
    SAML_CONFIG["xmlsec_binary"] = _saml_xmlsec
else:
    SAML_ATTRIBUTE_MAPPING = {}
    SAML_CONFIG: dict[str, object] = {}
