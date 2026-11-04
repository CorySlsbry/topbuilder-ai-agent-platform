"""PURE Stripe webhook signature verification — no stripe SDK dependency.

Stripe signs each webhook delivery with a `Stripe-Signature` header of the form

    t=<unix_ts>,v1=<hex_hmac>[,v1=<hex_hmac>...]

where each v1 is HMAC-SHA256(secret, f"{t}.{raw_body}"). Multiple v1 entries appear while an
endpoint secret is being rolled — the signature is valid if ANY v1 matches. Verification is
constant-time (hmac.compare_digest) and replay-bounded: |now - t| must be within `tolerance`
seconds (default 300, Stripe's documented recommendation). `now` is injectable for tests.

Deterministic and total: malformed input returns a failed parse / False — it NEVER raises.
"""
from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_TOLERANCE_SECONDS = 300


def parse_sig_header(header: str | None) -> tuple[int | None, list[str]]:
    """Parse a Stripe-Signature header into (timestamp, [v1 signatures]).

    A missing/malformed timestamp yields None; unknown schemes (v0, ...) are ignored. Never raises.
    """
    ts: int | None = None
    v1s: list[str] = []
    if not header or not isinstance(header, str):
        return None, []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if key == "t":
            try:
                ts = int(value)
            except ValueError:
                ts = None
        elif key == "v1" and value:
            v1s.append(value)
    return ts, v1s


def verify(
    raw_body: bytes,
    header: str,
    secret: str,
    *,
    now: int | None = None,
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """True iff `header` carries a fresh, valid v1 HMAC of `raw_body` under `secret`. Total —
    never raises."""
    if not secret:
        return False  # fail closed: an unset/empty secret can never verify anything
    ts, v1s = parse_sig_header(header)
    if ts is None or not v1s:
        return False
    if now is None:
        now = int(time.time())
    if abs(now - ts) > tolerance:
        return False  # stale (or implausibly future-dated) delivery — replay window exceeded
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in v1s)
