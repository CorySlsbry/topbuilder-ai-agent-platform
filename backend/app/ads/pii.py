"""Pure PII normalization + SHA-256 hashing for ad-platform conversion uploads.

Meta's Conversions API and Google's Enhanced Conversions both require customer-match identifiers to be
**normalized then SHA-256 hashed (lowercase hex)** before they ever leave our servers — the platform
matches on the hash, never the plaintext. The normalization rules below follow both specs:

  * email — trim surrounding whitespace, lowercase, then sha256.
  * phone — strip to E.164 digits (drop ``+``, spaces, punctuation), then sha256.

These functions are PURE and MUST NOT log their inputs: an email/phone is raw PII and the whole point
of hashing is that the plaintext is never persisted or printed. Callers pass the hex digest onward.
"""
from __future__ import annotations

import hashlib
import re

# ASCII-only: E.164 phone digits are 0-9. ``\D`` with Python's default Unicode regex would *keep*
# non-ASCII Unicode digits (e.g. Kaithi U+110F0), producing a hash that no platform would match —
# so we strip everything that is not an ASCII 0-9.
_NON_ASCII_DIGITS = re.compile(r"[^0-9]", re.ASCII)


def normalize_email(email: str) -> str:
    """Trim + lowercase an email per the Meta CAPI / Google Enhanced-Conversions spec."""
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """Reduce a phone number to its E.164 digits (no ``+``, spaces, or punctuation).

    The caller is responsible for supplying a number that already carries its country code (E.164);
    this only strips everything that is not a digit, e.g. ``"+1 (415) 555-1234"`` -> ``"14155551234"``.
    """
    return _NON_ASCII_DIGITS.sub("", phone)


def sha256_hex(value: str) -> str:
    """Lowercase hex SHA-256 of ``value`` (already-normalized input)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_email(email: str) -> str:
    """Normalize then SHA-256 an email (the value sent to Meta CAPI / Google Enhanced Conversions)."""
    return sha256_hex(normalize_email(email))


def hash_phone(phone: str) -> str:
    """Normalize to E.164 digits then SHA-256 a phone number."""
    return sha256_hex(normalize_phone(phone))
