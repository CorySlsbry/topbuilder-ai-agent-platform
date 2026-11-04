"""Oracle + property tests for ad-platform PII normalization + hashing (PURE, no DB).

Every expected hash is an INDEPENDENT hand-computed oracle — the exact SHA-256 hex is written here as a
literal (precomputed with Python's hashlib over the normalized string), never read back from the function
under test. Meta CAPI + Google Enhanced-Conversions both require lowercase-trim-then-sha256 for email and
digits-only-E.164-then-sha256 for phone.
"""
from __future__ import annotations

import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.ads.pii import (
    hash_email,
    hash_phone,
    normalize_email,
    normalize_phone,
    sha256_hex,
)

# Independent oracles: sha256('test@example.com') and sha256('16155550142').
EMAIL_HEX = "973dfe463ec85785f5f95af5ba3906eedb2d931c24e69824a89ea65dba4e813b"
PHONE_HEX = "d9b3852bb0e17d89d2275e43c7cf19bc70883891390c8d6fdb91e5fcbf5fa80a"


class TestNormalizeEmail:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Test@Example.com ", "test@example.com"),
            ("  USER@DOMAIN.IO", "user@domain.io"),
            ("already@lower.com", "already@lower.com"),
            ("\tMixed@Case.Net\n", "mixed@case.net"),
        ],
    )
    def test_known(self, raw: str, expected: str) -> None:
        assert normalize_email(raw) == expected


class TestNormalizePhone:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("+1 (615) 555-0142", "16155550142"),
            ("+1-415-555-1234", "14155551234"),
            ("14155551234", "14155551234"),
            ("+44 20 7946 0958", "442079460958"),
        ],
    )
    def test_known(self, raw: str, expected: str) -> None:
        assert normalize_phone(raw) == expected


class TestSha256Hex:
    def test_matches_hashlib_oracle(self) -> None:
        assert sha256_hex("test@example.com") == EMAIL_HEX

    def test_empty_string_oracle(self) -> None:
        assert sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestHashEmail:
    def test_normalizes_before_hashing(self) -> None:
        # The whole point: 'Test@Example.com ' must hash IDENTICALLY to 'test@example.com'.
        assert hash_email("Test@Example.com ") == EMAIL_HEX

    def test_already_normalized_matches(self) -> None:
        assert hash_email("test@example.com") == EMAIL_HEX

    @pytest.mark.parametrize(
        "raw", ["Test@Example.com ", "  TEST@example.COM", "test@example.com", "\ttest@example.com\n"]
    )
    def test_all_casings_collapse_to_one_hash(self, raw: str) -> None:
        assert hash_email(raw) == EMAIL_HEX


class TestHashPhone:
    def test_strips_to_e164_then_hashes(self) -> None:
        assert hash_phone("+1 (615) 555-0142") == PHONE_HEX

    def test_already_digits_matches(self) -> None:
        assert hash_phone("16155550142") == PHONE_HEX


class TestProperties:
    @given(st.emails())
    def test_hash_equals_sha256_of_normalized(self, email: str) -> None:
        # Independent oracle: re-derive the digest from the normalized string via stdlib hashlib.
        expected = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        assert hash_email(email) == expected

    @given(st.text(alphabet="0123456789", min_size=1, max_size=15))
    def test_digit_phone_roundtrips_through_hashlib(self, digits: str) -> None:
        expected = hashlib.sha256(digits.encode("utf-8")).hexdigest()
        assert hash_phone(digits) == expected

    @given(st.text(max_size=40))
    def test_normalize_phone_keeps_only_digits(self, raw: str) -> None:
        out = normalize_phone(raw)
        assert out == "".join(c for c in raw if c.isascii() and c.isdigit())

    @given(st.text(min_size=0, max_size=64))
    def test_sha256_hex_is_64_lowercase_hex(self, value: str) -> None:
        out = sha256_hex(value)
        assert len(out) == 64
        assert out == out.lower()
        assert all(c in "0123456789abcdef" for c in out)
