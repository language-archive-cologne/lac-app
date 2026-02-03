"""Tests for ALTCHA proof-of-work service."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from lacos.storage.services.altcha_service import AltchaService


class TestAltchaService:
    """Tests for AltchaService."""

    @pytest.fixture
    def service(self):
        """Create an AltchaService instance with test settings."""
        with patch.object(AltchaService, '__init__', lambda self: None):
            svc = AltchaService()
            svc.hmac_key = 'test-secret-key-12345678'
            svc.max_number = 50000
            svc.expires_seconds = 300
            svc.CACHE_KEY_PREFIX = 'altcha:challenge'
            return svc

    @pytest.fixture
    def valid_payload_dict(self):
        """Return a valid payload dict for testing."""
        return {
            'algorithm': 'SHA-256',
            'challenge': 'abc123',
            'number': 12345,
            'salt': 'random-salt-value',
            'signature': 'unique-signature-abc123',
        }

    @pytest.fixture
    def valid_payload_base64(self, valid_payload_dict):
        """Return a valid base64-encoded payload."""
        json_str = json.dumps(valid_payload_dict)
        return base64.b64encode(json_str.encode()).decode()

    def test_extract_signature_from_dict(self, service, valid_payload_dict):
        """Test signature extraction from dict payload."""
        sig = service._extract_signature(valid_payload_dict)
        assert sig == 'unique-signature-abc123'

    def test_extract_signature_from_base64(self, service, valid_payload_base64):
        """Test signature extraction from base64 payload."""
        sig = service._extract_signature(valid_payload_base64)
        assert sig == 'unique-signature-abc123'

    def test_extract_signature_empty_on_invalid_base64(self, service):
        """Test signature extraction returns empty string on invalid base64."""
        sig = service._extract_signature('not-valid-base64!!!')
        assert sig == ''

    def test_extract_signature_empty_on_missing_key(self, service):
        """Test signature extraction returns empty string when key missing."""
        payload = {'algorithm': 'SHA-256', 'challenge': 'abc'}
        sig = service._extract_signature(payload)
        assert sig == ''

    @pytest.mark.django_db
    @patch('lacos.storage.services.altcha_service.altcha.verify_solution')
    @patch('lacos.storage.services.altcha_service.cache')
    def test_verify_solution_success(
        self, mock_cache, mock_verify, service, valid_payload_dict
    ):
        """Test successful verification marks solution as used."""
        mock_verify.return_value = (True, None)
        mock_cache.add.return_value = True  # Successfully added (not duplicate)

        is_valid, error = service.verify_solution(valid_payload_dict)

        assert is_valid is True
        assert error is None
        mock_cache.add.assert_called_once()

    @pytest.mark.django_db
    @patch('lacos.storage.services.altcha_service.altcha.verify_solution')
    @patch('lacos.storage.services.altcha_service.cache')
    def test_verify_solution_replay_rejected(
        self, mock_cache, mock_verify, service, valid_payload_dict
    ):
        """Test replay attack is rejected via atomic cache.add()."""
        mock_verify.return_value = (True, None)
        mock_cache.add.return_value = False  # Key already exists (replay!)

        is_valid, error = service.verify_solution(valid_payload_dict)

        assert is_valid is False
        assert error == "Solution already used"

    @pytest.mark.django_db
    @patch('lacos.storage.services.altcha_service.altcha.verify_solution')
    @patch('lacos.storage.services.altcha_service.cache')
    def test_verify_solution_invalid_rejected(
        self, mock_cache, mock_verify, service, valid_payload_dict
    ):
        """Test invalid solution is rejected before cache check."""
        mock_verify.return_value = (False, "Invalid signature")

        is_valid, error = service.verify_solution(valid_payload_dict)

        assert is_valid is False
        assert error == "Invalid signature"
        mock_cache.add.assert_not_called()  # Cache not touched for invalid

    @pytest.mark.django_db
    @patch('lacos.storage.services.altcha_service.altcha.verify_solution')
    @patch('lacos.storage.services.altcha_service.cache')
    def test_verify_solution_base64_success(
        self, mock_cache, mock_verify, service, valid_payload_base64
    ):
        """Test base64 verification works correctly."""
        mock_verify.return_value = (True, None)
        mock_cache.add.return_value = True

        is_valid, error = service.verify_solution_base64(valid_payload_base64)

        assert is_valid is True
        assert error is None

    def test_verify_solution_base64_empty_rejected(self, service):
        """Test empty base64 payload is rejected."""
        is_valid, error = service.verify_solution_base64('')

        assert is_valid is False
        assert "Invalid payload" in error

    def test_verify_solution_base64_none_rejected(self, service):
        """Test None payload is rejected."""
        is_valid, error = service.verify_solution_base64(None)

        assert is_valid is False
        assert "Invalid payload" in error


class TestAltchaReplayProtection:
    """Integration tests for replay protection using Django cache."""

    @pytest.mark.django_db
    def test_same_solution_rejected_on_second_use(self):
        """Test that the same solution cannot be used twice."""
        # Create real service instance
        with patch('lacos.storage.services.altcha_service.settings') as mock_settings:
            mock_settings.ALTCHA_HMAC_KEY = 'test-key-for-replay-test'
            mock_settings.ALTCHA_MAX_NUMBER = 1000
            mock_settings.ALTCHA_EXPIRES_SECONDS = 60
            mock_settings.SECRET_KEY = 'fallback-key'

            service = AltchaService()

            # Create a challenge and solve it
            challenge = service.create_challenge()

            # Import altcha to solve the challenge
            import altcha
            solution = altcha.solve_challenge(
                challenge=challenge['challenge'],
                salt=challenge['salt'],
                algorithm=challenge['algorithm'],
                max_number=challenge['maxnumber'],
                start=0,
            )

            # Build the solution payload
            payload = {
                'algorithm': challenge['algorithm'],
                'challenge': challenge['challenge'],
                'number': solution.number,
                'salt': challenge['salt'],
                'signature': challenge['signature'],
            }

            # First verification should succeed
            is_valid1, error1 = service.verify_solution(payload)
            assert is_valid1 is True, f"First verification failed: {error1}"

            # Second verification with same payload should fail (replay)
            is_valid2, error2 = service.verify_solution(payload)
            assert is_valid2 is False
            assert error2 == "Solution already used"
