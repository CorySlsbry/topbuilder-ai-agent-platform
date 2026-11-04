"""Oracle tests for the PURE Stripe webhook signature verifier (app/tripwires/stripe_sig.py).

No stripe SDK, no network, no clock: `now` is injected. The scheme is Stripe's documented one —
header `t=<unix>,v1=<hex>[,v1=<hex>...]`, signed payload `f"{t}.{raw_body}"`, HMAC-SHA256 with the
endpoint's webhook secret, constant-time compare, |now - t| <= tolerance (default 300s).
"""
from __future__ import annotations

import hashlib
import hmac

from app.tripwires import stripe_sig

SECRET = "whsec_test_oracle_secret"
TS = 1700000000
BODY = b'{"id":"evt_test_1","type":"checkout.session.completed"}'
# Hand-computed oracle: hmac.new(SECRET, f"{TS}." + BODY, sha256).hexdigest()
#   = HMAC-SHA256("whsec_test_oracle_secret",
#                 b'1700000000.{"id":"evt_test_1","type":"checkout.session.completed"}')
V1 = "6915d860ed65718bb08a12d349c7e2f749990de3938bdaf16348ac1b185090b9"


def _sign(body: bytes, secret: str, ts: int) -> str:
    return hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


class TestParseSigHeader:
    def test_parses_timestamp_and_single_v1(self) -> None:
        ts, v1s = stripe_sig.parse_sig_header(f"t={TS},v1={V1}")
        assert ts == TS
        assert v1s == [V1]

    def test_parses_multiple_v1_entries(self) -> None:
        ts, v1s = stripe_sig.parse_sig_header(f"t={TS},v1=deadbeef,v1={V1}")
        assert ts == TS
        assert v1s == ["deadbeef", V1]

    def test_ignores_other_schemes(self) -> None:
        ts, v1s = stripe_sig.parse_sig_header(f"t={TS},v0=oldsig,v1={V1}")
        assert ts == TS
        assert v1s == [V1]

    def test_malformed_headers_do_not_raise(self) -> None:
        headers = ("", "garbage", "t=abc,v1=zz", f"v1={V1}", "t=,v1=", "t=123", ",,,", "=", None)
        for header in headers:
            ts, v1s = stripe_sig.parse_sig_header(header)  # type: ignore[arg-type]
            # Either the timestamp or the v1 list degrades; never an exception.
            assert ts is None or isinstance(ts, int)
            assert isinstance(v1s, list)

    def test_missing_timestamp_yields_none(self) -> None:
        ts, v1s = stripe_sig.parse_sig_header(f"v1={V1}")
        assert ts is None
        assert v1s == [V1]


class TestVerify:
    def test_hand_computed_oracle_passes(self) -> None:
        assert stripe_sig.verify(BODY, f"t={TS},v1={V1}", SECRET, now=TS) is True
        # And the oracle constant really is the HMAC we claim it is.
        assert _sign(BODY, SECRET, TS) == V1

    def test_wrong_secret_fails(self) -> None:
        assert stripe_sig.verify(BODY, f"t={TS},v1={V1}", "whsec_wrong", now=TS) is False

    def test_tampered_body_fails(self) -> None:
        assert stripe_sig.verify(BODY + b" ", f"t={TS},v1={V1}", SECRET, now=TS) is False

    def test_stale_timestamp_fails(self) -> None:
        # 301s in the past — one past the default 300s tolerance.
        assert stripe_sig.verify(BODY, f"t={TS},v1={V1}", SECRET, now=TS + 301) is False

    def test_future_timestamp_fails(self) -> None:
        assert stripe_sig.verify(BODY, f"t={TS},v1={V1}", SECRET, now=TS - 301) is False

    def test_within_tolerance_passes(self) -> None:
        assert stripe_sig.verify(BODY, f"t={TS},v1={V1}", SECRET, now=TS + 300) is True

    def test_custom_tolerance_is_honored(self) -> None:
        header = f"t={TS},v1={V1}"
        assert stripe_sig.verify(BODY, header, SECRET, now=TS + 60, tolerance=30) is False
        assert stripe_sig.verify(BODY, header, SECRET, now=TS + 60, tolerance=120) is True

    def test_multiple_v1_one_valid_passes(self) -> None:
        header = f"t={TS},v1=deadbeefdeadbeef,v1={V1}"
        assert stripe_sig.verify(BODY, header, SECRET, now=TS) is True

    def test_multiple_v1_none_valid_fails(self) -> None:
        header = f"t={TS},v1=deadbeefdeadbeef,v1=cafebabecafebabe"
        assert stripe_sig.verify(BODY, header, SECRET, now=TS) is False

    def test_malformed_header_fails_without_raising(self) -> None:
        for header in ("", "garbage", "t=abc,v1=zz", "t=123", f"v1={V1}", None):
            assert stripe_sig.verify(BODY, header, SECRET, now=TS) is False  # type: ignore[arg-type]

    def test_empty_secret_fails(self) -> None:
        assert stripe_sig.verify(BODY, f"t={TS},v1={V1}", "", now=TS) is False
