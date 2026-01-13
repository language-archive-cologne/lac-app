import subprocess

from django.conf import settings


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
        "SAML_LOGIN_ENABLED": getattr(settings, "SAML_LOGIN_ENABLED", False),
    }


# Cache the git commit hash at module load time
def _get_git_commit_hash():
    """Get the short git commit hash, cached at startup."""
    from pathlib import Path

    # Try reading directly from .git directory (works without git command)
    try:
        git_dir = Path(__file__).resolve().parent.parent.parent / ".git"
        head_file = git_dir / "HEAD"

        if head_file.exists():
            head_content = head_file.read_text().strip()

            # HEAD contains either a ref or a direct commit hash
            if head_content.startswith("ref:"):
                # It's a reference like "ref: refs/heads/dev"
                ref_path = git_dir / head_content.split("ref:")[1].strip()
                if ref_path.exists():
                    commit_hash = ref_path.read_text().strip()
                    return commit_hash[:7]
            else:
                # It's a direct commit hash (detached HEAD)
                return head_content[:7]
    except Exception:
        pass

    # Fallback: try git command
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


_GIT_COMMIT_HASH = _get_git_commit_hash()


def version_info(request):
    """Expose version information in templates."""
    return {
        "VERSION_COMMIT": _GIT_COMMIT_HASH,
    }
