"""Regression lock for the fail-fast production-config guard (audit 2026-06-18, extended 2026-07-01).

A production service that forgot to flip AUTH_MODE / lock CORS / rotate the secret / allowlist an
operator / enable HSTS / verify DB TLS must CRASH at boot, not run insecurely. The guard is
duck-typed on the settings attrs, so we exercise it with stand-ins.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.main import _assert_production_config


def _prod_ns(**over) -> SimpleNamespace:
    """A fully-valid production settings stand-in; override one field per test case."""
    base = dict(
        is_dev=False,
        auth_mode="jwks",
        jwt_secret="k" * 40,
        allowed_origins="https://app.example.com",
        trusted_hosts="api.example.com",
        platform_operator_email_set={"op@example.com"},
        hsts_enabled=True,
        db_ssl_verify=True,
        actions_enabled=False,
        email_send_mode="fixture",
        resend_api_key=None,
        servicetitan_mode="fixture",
        servicetitan_client_secret=None,
        webhook_signing_secret="w" * 32,
        cron_secret="c" * 32,
        credential_encryption_key="e" * 44,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_dev_is_a_noop():
    _assert_production_config(SimpleNamespace(is_dev=True))  # ENV=dev: anything goes


def test_prod_with_dev_auth_refuses_to_boot():
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        _assert_production_config(_prod_ns(auth_mode="dev"))


def test_prod_with_default_secret_or_wildcards_refuses_to_boot():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _assert_production_config(_prod_ns(jwt_secret="change-me"))
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        _assert_production_config(_prod_ns(allowed_origins="*"))


def test_prod_without_operator_allowlist_refuses_to_boot():
    with pytest.raises(RuntimeError, match="PLATFORM_OPERATOR_EMAILS"):
        _assert_production_config(_prod_ns(platform_operator_email_set=set()))


def test_prod_without_hsts_refuses_to_boot():
    with pytest.raises(RuntimeError, match="HSTS_ENABLED"):
        _assert_production_config(_prod_ns(hsts_enabled=False))


def test_prod_without_db_tls_verify_only_warns():
    # DB_SSL_VERIFY=false warns (the Supabase pooler CA isn't pinnable yet); it must NOT brick boot.
    _assert_production_config(_prod_ns(db_ssl_verify=False))


def test_prod_actions_on_with_live_mode_but_no_creds_refuses_to_boot():
    # Master switch ON + a live provider without credentials = approved actions die at the executor.
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        _assert_production_config(
            _prod_ns(actions_enabled=True, email_send_mode="live", resend_api_key=None)
        )
    with pytest.raises(RuntimeError, match="ServiceTitan"):
        _assert_production_config(
            _prod_ns(actions_enabled=True, servicetitan_mode="live", servicetitan_client_secret=None)
        )
    # Same live modes WITH creds boot fine.
    _assert_production_config(
        _prod_ns(actions_enabled=True, email_send_mode="live", resend_api_key="re_x",
                 servicetitan_mode="live", servicetitan_client_secret="s3cret")
    )


def test_unset_optional_secrets_warn_but_do_not_block_boot():
    _assert_production_config(
        _prod_ns(webhook_signing_secret=None, cron_secret=None, credential_encryption_key=None)
    )  # dormant fail-closed features: warn, don't crash


def test_properly_configured_prod_boots():
    _assert_production_config(_prod_ns())  # no exception
