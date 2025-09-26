from django.conf import settings

# Directory name used for OCFL content payloads
OCFL_DATA_DIR: str = getattr(settings, "OCFL_DATA_DIRECTORY", "data")
