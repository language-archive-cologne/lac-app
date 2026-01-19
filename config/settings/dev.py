"""Development settings that mirror production S3 usage with verbose logging."""

from .production import *  # noqa

# General
# ------------------------------------------------------------------------------
DEBUG = True

# Add dev server to allowed hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["lacos.uni-koeln.de"]) + [
    "dev.lacos.uni-koeln.de",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]

# Relax HTTPS-only redirects for local development unless explicitly enabled
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

# Email
# ------------------------------------------------------------------------------
# Use console backend by default to avoid sending real mail while developing
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

# Logging
# ------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "boto3": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "botocore": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "urllib3": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "lacos": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "lacos.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# S3 URL overrides
# ------------------------------------------------------------------------------
use_browser_static = env.bool("DJANGO_USE_BROWSER_STATIC", default=False)
if use_browser_static:
    browser_endpoint = env("AWS_S3_BROWSER_ENDPOINT_URL", default=None)
    if browser_endpoint:
        browser_endpoint = browser_endpoint.rstrip("/")
        MEDIA_URL = f"{browser_endpoint}/media/"
        STATIC_URL = f"{browser_endpoint}/static/"
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(APPS_DIR / "media")},
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    MEDIA_URL = "/media/"
    STATIC_URL = "/static/"

# SAML defaults for dev
# ------------------------------------------------------------------------------
if SAML_LOGIN_ENABLED:
    SAML_CONFIG = dict(SAML_CONFIG)
    _saml_key_file = env("SAML_SP_KEY_FILE", default="/etc/shibboleth/sp-key.pem")
    _saml_cert_file = env("SAML_SP_CERT_FILE", default="/etc/shibboleth/sp-cert.pem")
    SAML_CONFIG["key_file"] = _saml_key_file
    SAML_CONFIG["cert_file"] = _saml_cert_file
    SAML_CONFIG["encryption_keypairs"] = [
        {"key_file": _saml_key_file, "cert_file": _saml_cert_file}
    ]
