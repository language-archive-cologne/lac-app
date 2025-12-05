"""
Tests for text normalization utilities.
"""
import unicodedata

from lacos.utils.text import normalize_nfc, normalize_nfc_strip


class TestNormalizeNfc:
    """Tests for the normalize_nfc function."""

    def test_none_returns_none(self):
        assert normalize_nfc(None) is None

    def test_empty_string_unchanged(self):
        assert normalize_nfc("") == ""

    def test_ascii_unchanged(self):
        assert normalize_nfc("hello world") == "hello world"

    def test_nfc_string_unchanged(self):
        """NFC string should remain unchanged."""
        # NFC form of u-umlaut (single character)
        nfc = "m\u00fcller"  # muller with u-umlaut
        assert normalize_nfc(nfc) == nfc

    def test_nfd_converted_to_nfc(self):
        """NFD string should be converted to NFC."""
        # NFD form: u + combining diaeresis
        nfd = "mu\u0308ller"
        # NFC form: u-umlaut as single character
        nfc = "m\u00fcller"

        result = normalize_nfc(nfd)
        assert result == nfc
        assert len(result) == 6  # NFC is shorter

    def test_mixed_nfd_nfc_normalized(self):
        """Mixed NFD/NFC string should be fully normalized."""
        # Mix of NFD and NFC
        mixed = "caf\u00e9 m\u00fcller e\u0301"  # cafe (NFC), muller (NFC), e + acute (NFD)
        result = normalize_nfc(mixed)
        # All should be NFC now
        assert result == unicodedata.normalize("NFC", mixed)

    def test_various_combining_characters(self):
        """Various combining characters should be composed."""
        # a + combining ring above = a-ring
        nfd = "a\u030a"
        nfc = "\u00e5"
        assert normalize_nfc(nfd) == nfc

        # n + combining tilde = n-tilde
        nfd = "n\u0303"
        nfc = "\u00f1"
        assert normalize_nfc(nfd) == nfc

        # o + combining acute = o-acute
        nfd = "o\u0301"
        nfc = "\u00f3"
        assert normalize_nfc(nfd) == nfc

    def test_hangul_normalization(self):
        """Korean Hangul should be normalized."""
        # Hangul syllable can be decomposed or composed
        composed = "\uac00"  # ga
        decomposed = "\u1100\u1161"  # g + a
        assert normalize_nfc(decomposed) == composed

    def test_preserves_non_composable(self):
        """Characters without NFC equivalents should be preserved."""
        # Characters that don't compose
        text = "hello \u0300 world"  # standalone combining grave
        result = normalize_nfc(text)
        assert "\u0300" in result  # Still present

    def test_email_with_unicode(self):
        """Email addresses with unicode should be normalized."""
        # NFD form
        email_nfd = "mu\u0308ller@uni-ko\u0308ln.de"
        # NFC form
        email_nfc = "m\u00fcller@uni-k\u00f6ln.de"
        assert normalize_nfc(email_nfd) == email_nfc


class TestNormalizeNfcStrip:
    """Tests for the normalize_nfc_strip function."""

    def test_none_returns_none(self):
        assert normalize_nfc_strip(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_nfc_strip("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_nfc_strip("   ") is None
        assert normalize_nfc_strip("\t\n") is None

    def test_strips_whitespace(self):
        assert normalize_nfc_strip("  hello  ") == "hello"
        assert normalize_nfc_strip("\thello\n") == "hello"

    def test_normalizes_and_strips(self):
        # NFD with whitespace
        nfd = "  mu\u0308ller  "
        nfc = "m\u00fcller"
        assert normalize_nfc_strip(nfd) == nfc

    def test_preserves_internal_whitespace(self):
        assert normalize_nfc_strip("  hello world  ") == "hello world"
