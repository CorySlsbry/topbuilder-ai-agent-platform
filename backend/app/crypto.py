"""Application-layer encryption for credentials at rest (ServiceTitan / QuickBooks / provider tokens).

Ciphertext uses **AES-256-GCM** (authenticated encryption): a fresh random 96-bit nonce per message,
stored as ``v2:gcm:`` + urlsafe-base64(nonce || ciphertext || tag). The key comes from
``CREDENTIAL_ENCRYPTION_KEY`` — a urlsafe-base64-encoded **32-byte (AES-256)** key that lives in
Secret Manager in prod, never in the database or the repo.

This is the app-layer field encryption layered on top of the storage layer, which is itself AES-256
at rest (Supabase/Postgres on AWS for the primary DB + backups; Google Cloud for Cloud Run, logs and
secrets). So credentials are AES-256-encrypted at every layer.

Legacy note: tokens written by the previous Fernet (AES-128-CBC + HMAC) cipher still decrypt — the
same 32-byte key reconstructs the Fernet key — so the upgrade needs no data migration. New writes are
always AES-256-GCM. Rotate by re-encrypting (decrypt with the old key, encrypt with the new).

Key rotation: ``CREDENTIAL_ENCRYPTION_KEY`` is the **primary** key — every encrypt uses it. The
optional ``CREDENTIAL_ENCRYPTION_KEY_OLD`` setting holds a comma-separated list of **retired** keys
that are accepted for **decrypt only**, so ciphertext written under a previous key still reads back
during the rotation window. ``rotate_ciphertext`` decrypts (primary, any old key, or legacy Fernet)
and re-encrypts under the primary — run the ``rotate_credentials`` script to sweep the vault, then
drop the old key from ``CREDENTIAL_ENCRYPTION_KEY_OLD``. See docs/CREDENTIAL_ROTATION.md.
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_SCHEME = "v2:gcm:"  # marks AES-256-GCM ciphertext; legacy Fernet blobs carry no scheme prefix
_NONCE_BYTES = 12  # 96-bit nonce, the GCM standard


def _load_key(key: str | bytes | None) -> bytes:
    """Decode the configured key to its raw 32 bytes, rejecting anything weaker than AES-256."""
    if not key:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is not set")
    raw = key.encode() if isinstance(key, str) else key
    try:
        decoded = base64.urlsafe_b64decode(raw)
    except Exception as exc:  # noqa: BLE001 — any decode failure is a misconfigured key
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be urlsafe-base64") from exc
    if len(decoded) != 32:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must decode to 32 bytes (AES-256)")
    return decoded


def _load_old_keys(old_keys: str | bytes | list[str | bytes] | None) -> list[bytes]:
    """Decode the retired DECRYPT-ONLY keys (comma-separated string or list) to their raw 32 bytes.

    Each entry is validated like the primary key; a misconfigured retired key fails loudly rather than
    silently widening the decrypt surface. Returns ``[]`` when no old keys are configured.
    """
    if not old_keys:
        return []
    if isinstance(old_keys, (str, bytes)):
        raw = old_keys.decode() if isinstance(old_keys, bytes) else old_keys
        items: list[str | bytes] = [k for k in raw.split(",") if k.strip()]
    else:
        items = list(old_keys)
    return [_load_key(item) for item in items if item]


class CredentialCipher:
    """AES-256-GCM field cipher with primary-encrypt / many-keys-decrypt key rotation.

    ``key`` is the **primary** key used for every encrypt. ``old_keys`` are retired keys accepted for
    decrypt only (so ciphertext written under a previous key still reads during the rotation window).
    """

    def __init__(
        self,
        key: str | bytes | None,
        old_keys: str | bytes | list[str | bytes] | None = None,
    ) -> None:
        self.key_bytes = _load_key(key)
        self._aes = AESGCM(self.key_bytes)
        self.old_key_bytes = _load_old_keys(old_keys)
        self._old_aes = [AESGCM(k) for k in self.old_key_bytes]

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode(), None)
        return _SCHEME + base64.urlsafe_b64encode(nonce + ciphertext).decode()

    def decrypt(self, ciphertext: str) -> str:
        if ciphertext.startswith(_SCHEME):
            blob = base64.urlsafe_b64decode(ciphertext[len(_SCHEME) :].encode())
            nonce, body = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
            for aes in (self._aes, *self._old_aes):  # primary first, then each retired key
                try:
                    return aes.decrypt(nonce, body, None).decode()
                except InvalidTag:
                    continue
            raise ValueError("credential decryption failed (authentication tag mismatch)")
        return self._decrypt_legacy_fernet(ciphertext)

    def _decrypt_legacy_fernet(self, ciphertext: str) -> str:
        """Decrypt a token written by the old Fernet (AES-128) cipher, keyed by the same 32 bytes.

        Tries the primary key first, then any retired key — a Fernet blob predates GCM, so it may be
        keyed by a now-retired key during rotation.
        """
        from cryptography.fernet import Fernet, InvalidToken

        for key_bytes in (self.key_bytes, *self.old_key_bytes):
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            try:
                return Fernet(fernet_key).decrypt(ciphertext.encode()).decode()
            except InvalidToken:
                continue
        raise ValueError("credential decryption failed")

    def rotate_ciphertext(self, old_ciphertext: str) -> str:
        """Re-encrypt a stored secret under the **primary** key.

        Decrypts ``old_ciphertext`` with the primary key, any retired key, or the legacy Fernet path,
        then re-encrypts under the current primary AES-256-GCM key. Already-primary ciphertext simply
        round-trips to a fresh (re-nonced) primary ciphertext, so the sweep is safe to re-run.
        """
        return self.encrypt(self.decrypt(old_ciphertext))


@lru_cache
def get_cipher() -> CredentialCipher:
    settings = get_settings()
    # Read the retired-key list defensively: the setting is optional and older config objects may not
    # define it, so fall back to None rather than raising on a missing attribute.
    old_keys = getattr(settings, "credential_encryption_key_old", None)
    return CredentialCipher(settings.credential_encryption_key, old_keys=old_keys)


def rotate_ciphertext(old_ciphertext: str) -> str:
    """Re-encrypt a stored secret under the configured primary key (module-level convenience).

    Uses the process-wide cipher (primary + retired keys from settings). See
    :meth:`CredentialCipher.rotate_ciphertext`.
    """
    return get_cipher().rotate_ciphertext(old_ciphertext)
