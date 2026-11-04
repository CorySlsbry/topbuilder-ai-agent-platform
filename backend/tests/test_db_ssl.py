"""The database connection pins TLS 1.2+ for remote hosts (encryption in transit)."""
from __future__ import annotations

import ssl

from app.db import db_ssl_context


def test_local_host_needs_no_tls_context() -> None:
    # Local dev Postgres talks over a loopback socket; no TLS context is forced.
    for url in (
        "postgresql+asyncpg://app_user:app_pw@localhost:5432/fieldops",
        "postgresql+asyncpg://app_user:app_pw@127.0.0.1:5432/fieldops",
    ):
        assert db_ssl_context(url) is None


def test_remote_host_pins_tls_1_2_minimum() -> None:
    ctx = db_ssl_context(
        "postgresql+asyncpg://app_user.ref:pw@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
    )
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_remote_default_is_encrypt_only_to_avoid_pooler_cert_breakage() -> None:
    # Default (verify off): still encrypted with TLS 1.2+, but does not fail on the pooler cert chain.
    ctx = db_ssl_context("postgresql+asyncpg://u:p@db.example.com:5432/postgres", verify=False)
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_remote_verify_mode_enables_full_validation() -> None:
    ctx = db_ssl_context("postgresql+asyncpg://u:p@db.example.com:5432/postgres", verify=True)
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2
