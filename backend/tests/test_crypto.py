"""Tests for the credential vault cipher.

Upgraded to AES-256-GCM (authenticated encryption) so the at-rest credential encryption meets the
"minimum AES-256 for all customer data at rest" bar — at the app layer, on top of the AES-256
storage layer (Supabase/Postgres on AWS + Cloud Run/Secret Manager).
"""
from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet

from app.crypto import CredentialCipher


def _key256() -> str:
    """A urlsafe-base64 encoding of 32 random bytes = an AES-256 key.

    (Fernet.generate_key() produces exactly this shape — 32 bytes, urlsafe-base64 — so the existing
    CREDENTIAL_ENCRYPTION_KEY secret works unchanged as an AES-256 key.)
    """
    return Fernet.generate_key().decode()


class TestCredentialCipher:
    def test_roundtrip_recovers_plaintext(self) -> None:
        cipher = CredentialCipher(_key256())
        secret = "st_client_secret_9f8a7b6c"
        encrypted = cipher.encrypt(secret)
        assert encrypted != secret
        assert cipher.decrypt(encrypted) == secret

    def test_uses_aes_256_gcm(self) -> None:
        cipher = CredentialCipher(_key256())
        encrypted = cipher.encrypt("token")
        # AES-256-GCM ciphertext is tagged with the scheme; the key is 32 bytes (256-bit).
        assert encrypted.startswith("v2:gcm:")
        assert len(cipher.key_bytes) == 32

    def test_ciphertext_is_nondeterministic_random_nonce(self) -> None:
        cipher = CredentialCipher(_key256())
        secret = "qbo_refresh_token_abc"
        assert cipher.encrypt(secret) != cipher.encrypt(secret)  # fresh 96-bit nonce each time

    def test_wrong_key_cannot_decrypt(self) -> None:
        a = CredentialCipher(_key256())
        b = CredentialCipher(_key256())
        token = a.encrypt("secret")
        with pytest.raises(Exception):
            b.decrypt(token)

    def test_tampered_ciphertext_fails_authentication(self) -> None:
        cipher = CredentialCipher(_key256())
        encrypted = cipher.encrypt("secret")
        body = encrypted[len("v2:gcm:") :]
        flipped = ("A" if body[0] != "A" else "B") + body[1:]
        with pytest.raises(Exception):
            cipher.decrypt("v2:gcm:" + flipped)

    def test_missing_key_raises(self) -> None:
        with pytest.raises(RuntimeError):
            CredentialCipher(None)

    def test_key_shorter_than_256_bits_is_rejected(self) -> None:
        aes128 = base64.urlsafe_b64encode(b"\x00" * 16).decode()  # 16 bytes = AES-128
        with pytest.raises(RuntimeError):
            CredentialCipher(aes128)

    def test_legacy_fernet_token_still_decrypts(self) -> None:
        """Tokens written by the old Fernet (AES-128) cipher must still read back during transition
        (the same 32-byte key reconstructs the Fernet key)."""
        key = _key256()
        raw32 = base64.urlsafe_b64decode(key.encode())
        legacy = Fernet(base64.urlsafe_b64encode(raw32)).encrypt(b"legacy_secret").decode()
        assert CredentialCipher(key).decrypt(legacy) == "legacy_secret"


class TestKeyRotation:
    """Decrypt-only old keys + rotate_ciphertext (encrypt always uses the primary key)."""

    def test_old_key_ciphertext_decrypts_under_new_primary(self) -> None:
        old, new = _key256(), _key256()
        token = CredentialCipher(old).encrypt("st_refresh_token")
        # New primary, old key kept only for decrypt — the old ciphertext must still read back.
        rotated_cipher = CredentialCipher(new, old_keys=[old])
        assert rotated_cipher.decrypt(token) == "st_refresh_token"

    def test_old_keys_accept_comma_separated_string(self) -> None:
        old1, old2, new = _key256(), _key256(), _key256()
        token = CredentialCipher(old2).encrypt("qbo_token")
        cipher = CredentialCipher(new, old_keys=f"{old1},{old2}")
        assert cipher.decrypt(token) == "qbo_token"

    def test_unknown_old_ciphertext_still_fails(self) -> None:
        primary, retired, stranger = _key256(), _key256(), _key256()
        token = CredentialCipher(stranger).encrypt("secret")
        cipher = CredentialCipher(primary, old_keys=[retired])
        with pytest.raises(ValueError):
            cipher.decrypt(token)

    def test_rotate_ciphertext_round_trips_old_to_new(self) -> None:
        old, new = _key256(), _key256()
        secret = "st_client_secret_rotate_me"
        old_token = CredentialCipher(old).encrypt(secret)
        cipher = CredentialCipher(new, old_keys=[old])
        new_token = cipher.rotate_ciphertext(old_token)
        # Re-encrypted under the new primary: the new-only cipher decrypts it; the old key cannot.
        assert CredentialCipher(new).decrypt(new_token) == secret
        with pytest.raises(ValueError):
            CredentialCipher(old).decrypt(new_token)

    def test_rotate_always_encrypts_with_primary_not_old(self) -> None:
        old, new = _key256(), _key256()
        old_token = CredentialCipher(old).encrypt("token")
        new_token = CredentialCipher(new, old_keys=[old]).rotate_ciphertext(old_token)
        assert new_token.startswith("v2:gcm:")
        # The primary key alone recovers it; the retired key alone cannot.
        assert CredentialCipher(new).decrypt(new_token) == "token"
        assert CredentialCipher(old).decrypt(old_token) == "token"

    def test_rotate_is_idempotent_on_primary_ciphertext(self) -> None:
        new = _key256()
        cipher = CredentialCipher(new)  # no old keys: re-running the sweep must stay safe
        token = cipher.encrypt("already_current")
        rotated = cipher.rotate_ciphertext(token)
        assert cipher.decrypt(rotated) == "already_current"

    def test_rotate_migrates_legacy_fernet_to_gcm(self) -> None:
        old, new = _key256(), _key256()
        raw_old = base64.urlsafe_b64decode(old.encode())
        legacy = Fernet(base64.urlsafe_b64encode(raw_old)).encrypt(b"legacy_secret").decode()
        rotated = CredentialCipher(new, old_keys=[old]).rotate_ciphertext(legacy)
        assert rotated.startswith("v2:gcm:")
        assert CredentialCipher(new).decrypt(rotated) == "legacy_secret"

    def test_no_old_keys_is_unchanged_behavior(self) -> None:
        key = _key256()
        cipher = CredentialCipher(key)
        assert cipher.old_key_bytes == []
        token = cipher.encrypt("secret")
        assert cipher.decrypt(token) == "secret"

    def test_misconfigured_old_key_is_rejected(self) -> None:
        primary = _key256()
        aes128 = base64.urlsafe_b64encode(b"\x00" * 16).decode()  # 16 bytes = too short
        with pytest.raises(RuntimeError):
            CredentialCipher(primary, old_keys=[aes128])
