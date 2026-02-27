"""ALTCHA proof-of-work service for protecting downloads from bots."""

import logging
import secrets
from typing import Optional, Tuple

from django.conf import settings
from django.core.cache import cache

import altcha

logger = logging.getLogger(__name__)


class AltchaService:
    """
    Service for generating and verifying ALTCHA proof-of-work challenges.

    This protects download endpoints from automated bots by requiring
    clients to solve a computational puzzle before receiving presigned URLs.
    """

    CACHE_KEY_PREFIX = "altcha:challenge"

    def __init__(self):
        # Secret key for HMAC - should be set in settings
        self.hmac_key = getattr(settings, 'ALTCHA_HMAC_KEY', None)
        if not self.hmac_key:
            # Generate a random key if not configured (not recommended for production)
            self.hmac_key = getattr(settings, 'SECRET_KEY', secrets.token_hex(32))
            logger.warning("ALTCHA_HMAC_KEY not set, using SECRET_KEY as fallback")

        # Challenge difficulty (higher = more computation required)
        # Default: 50000 iterations (~1-2 seconds on modern hardware)
        self.max_number = getattr(settings, 'ALTCHA_MAX_NUMBER', 50000)

        # Challenge expiration in seconds (default: 5 minutes)
        self.expires_seconds = getattr(settings, 'ALTCHA_EXPIRES_SECONDS', 300)

    def create_challenge(self) -> dict:
        """Create a new ALTCHA challenge.

        Returns:
            Dict with challenge data to send to the frontend widget.
        """
        from datetime import datetime, timedelta

        # Calculate expiration timestamp
        expires = datetime.now() + timedelta(seconds=self.expires_seconds)

        # Create the challenge using altcha library
        challenge = altcha.create_challenge(
            altcha.ChallengeOptions(
                hmac_key=self.hmac_key,
                max_number=self.max_number,
                expires=expires,
                algorithm='SHA-256',
            )
        )

        logger.debug("Created ALTCHA challenge", extra={"expires_seconds": self.expires_seconds})

        return {
            'algorithm': challenge.algorithm,
            'challenge': challenge.challenge,
            'maxnumber': challenge.max_number,
            'salt': challenge.salt,
            'signature': challenge.signature,
        }

    def _extract_signature(self, payload) -> str:
        """Extract signature from payload for replay protection.

        Args:
            payload: Can be dict, Payload object, or base64 string.

        Returns:
            Signature string or empty string if not found.
        """
        import base64
        import json

        if isinstance(payload, dict):
            return payload.get('signature', '')
        elif isinstance(payload, str):
            # Base64 encoded - decode to extract signature
            try:
                decoded = base64.b64decode(payload).decode('utf-8')
                data = json.loads(decoded)
                return data.get('signature', '')
            except Exception:
                return ''
        else:
            return getattr(payload, 'signature', '')

    def verify_solution(self, payload) -> Tuple[bool, Optional[str]]:
        """Verify an ALTCHA solution from the client.

        Args:
            payload: The solution payload from the frontend widget.
                     Can be dict, Payload object, or base64 string.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Get signature for replay protection (handles base64, dict, or object)
            sig = self._extract_signature(payload)

            # Verify the solution first
            is_valid, error = altcha.verify_solution(
                payload=payload,
                hmac_key=self.hmac_key,
                check_expires=True
            )

            if not is_valid:
                logger.warning("ALTCHA verification failed", extra={"error": error})
                return is_valid, error

            # Atomically mark as used to prevent race condition replays.
            # cache.add() returns False if key already exists, True if set.
            if sig:
                solution_key = f"{self.CACHE_KEY_PREFIX}:used:{sig}"
                if not cache.add(solution_key, True, timeout=self.expires_seconds):
                    logger.warning("ALTCHA solution replay attempt detected")
                    return False, "Solution already used"

            logger.debug("ALTCHA solution verified successfully")
            return True, None

        except Exception as e:
            logger.error("ALTCHA verification error", extra={"error": str(e)})
            return False, str(e)

    def verify_solution_base64(self, payload_base64: str) -> Tuple[bool, Optional[str]]:
        """Verify a base64-encoded ALTCHA solution.

        The ALTCHA widget submits solutions as base64-encoded JSON.

        Args:
            payload_base64: Base64-encoded solution from the widget.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not payload_base64 or not isinstance(payload_base64, str):
            return False, "Invalid payload: expected base64 string"

        try:
            return self.verify_solution(payload_base64)
        except Exception as e:
            logger.error("Failed to verify ALTCHA payload", extra={"error": str(e)})
            return False, f"Invalid payload format: {e}"


# Thread-safe singleton
_service_instance = None
_service_lock = None


def get_altcha_service() -> AltchaService:
    """Get the singleton AltchaService instance (thread-safe)."""
    global _service_instance, _service_lock

    if _service_lock is None:
        import threading
        _service_lock = threading.Lock()

    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = AltchaService()

    return _service_instance
