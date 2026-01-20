from django.conf import settings

# Directory name used for OCFL content payloads
OCFL_DATA_DIR: str = getattr(settings, "OCFL_DATA_DIRECTORY", "data")

# Web Access Control constants (aligned with KA3/KArchive API expectations)
WAC_AGENT: str = "foaf:Agent"
WAC_AUTHENTICATED_AGENT: str = "acl:AuthenticatedAgent"
WAC_READ: str = "acl:Read"

# Normalised access level labels
ACL_LEVEL_PUBLIC: str = "public"
ACL_LEVEL_ACADEMIC: str = "academic"
ACL_LEVEL_PRIVATE: str = "private"
