# ruff: noqa: E501
from .base import *  # noqa: F403
from .base import INSTALLED_APPS
from .base import MIDDLEWARE
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="wnacXjF44eumibtXfNQUTnlHxjoLwyJAAdCb5F29tXZ0ML7ioAZyIYAAwUF4htuH",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["localhost", "0.0.0.0", "127.0.0.1"]  # noqa: S104

# CACHES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    },
}

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend",
)

# django-debug-toolbar
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS += ["debug_toolbar"]
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": [
        "debug_toolbar.panels.redirects.RedirectsPanel",
        # Disable profiling panel due to an issue with Python 3.12:
        # https://github.com/jazzband/django-debug-toolbar/issues/1875
        "debug_toolbar.panels.profiling.ProfilingPanel",
    ],
    "SHOW_TEMPLATE_CONTEXT": True,
}
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips
INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]
if env("USE_DOCKER") == "yes":
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join(ip.split(".")[:-1] + ["1"]) for ip in ips]

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]


# S3/MinIO Settings for Local Development
# ------------------------------------------------------------------------------
USE_MINIO = env.bool("USE_MINIO", default=True)
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="http://minio:9000")
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="minioadmin")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="minioadmin")
# Bucket for ingesting data
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="lacos-ingest")
# Bucket for production/published data
AWS_PRODUCTION_BUCKET_NAME = env("AWS_PRODUCTION_BUCKET_NAME", default="lacos-production")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")

# Ensure the buckets exist on startup
# This is handled by the BucketService in the storage app

# Your stuff...
# ------------------------------------------------------------------------------

# Guidelines - use local mounted volume for development
GUIDELINES_REPO_URL = "/lac-guidelines"

# Huey configuration for development
# ------------------------------------------------------------------------------
# Uncomment this to use immediate mode during development
# HUEY = {**HUEY, 'immediate': True}  # Use immediate mode in development

# Logging
# ------------------------------------------------------------------------------
# Reduce high-volume queue/access logs in local development.
LOGGING = {
    **LOGGING,
    "root": {"level": "WARNING", "handlers": ["console"]},
    "loggers": {
        **LOGGING.get("loggers", {}),
        "api": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "consumer": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "huey": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "huey.consumer": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "huey.api": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "lacos.ingest.tasks": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "lacos.ingest.services.reindex_service": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
