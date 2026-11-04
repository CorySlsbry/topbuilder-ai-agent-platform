"""Pure tests for QuickBooks Online webhook signature verification (ADR 0010)."""
from __future__ import annotations

import base64
import hashlib
import hmac

from app.webhooks import verify_qbo_signature


def _intuit_signature(body: bytes, token: str) -> str:
    return base64.b64encode(hmac.new(token.encode(), body, hashlib.sha256).digest()).decode()


def test_qbo_signature_roundtrip_verifies():
    body = b'{"eventNotifications":[{"realmId":"123"}]}'
    token = "verifier-token-123"
    assert verify_qbo_signature(body, _intuit_signature(body, token), token) is True


def test_qbo_signature_rejects_wrong_verifier_token():
    body = b'{"x":1}'
    assert verify_qbo_signature(body, _intuit_signature(body, "right-token"), "wrong-token") is False


def test_qbo_signature_rejects_tampered_body():
    token = "t"
    sig = _intuit_signature(b'{"amount":100}', token)
    assert verify_qbo_signature(b'{"amount":999}', sig, token) is False


def test_qbo_signature_fails_closed_on_missing_inputs():
    assert verify_qbo_signature(b"{}", None, "token") is False
    assert verify_qbo_signature(b"{}", "sig", "") is False
