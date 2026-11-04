"""Guard test for the LOCKED QuickBooks Online OAuth scope decision.

The decision (owner's call, recorded in docs/QBO_SCOPE_DECISION.md):
  - QBO entitlement = Accounting API, READ-ONLY: the single scope
    ``com.intuit.quickbooks.accounting``. The Financial agent reads AR/AP aging, invoices, balance
    sheet, and P&L — nothing more.
  - We do NOT request ``com.intuit.quickbooks.payment`` (no card processing) or ``openid`` (no
    sign-in-with-Intuit), and we do NOT use QBO Payroll (payroll lives in ServiceTitan).

These asserts lock that in so the scope can't silently drift: widening it must update the decision doc
AND this test in the same change. We assert against the REAL ``Settings`` default and the REAL
``qbo_oauth`` builder (the scope value is not mocked).

``_env_file=None`` + clearing ``QUICKBOOKS_SCOPES`` from the environment makes the assertion hermetic:
it pins the in-code default, independent of any stray ``.env`` or shell override on the dev box.
"""
from __future__ import annotations

import urllib.parse

import pytest

from app.config import Settings
from app.integrations.quickbooks import qbo_oauth

# The one entitlement the product requests — Accounting API, read-only. Anything else is a deliberate,
# doc-backed widening, never a default.
ACCOUNTING_ONLY = "com.intuit.quickbooks.accounting"
# Scopes the decision explicitly EXCLUDES (asserted absent so a future paste can't sneak one in).
FORBIDDEN_SUBSTRINGS = ("payroll", "payment")


@pytest.fixture
def default_settings(monkeypatch) -> Settings:
    """The in-code default scope, hermetic to the environment (ignore .env + any QUICKBOOKS_SCOPES env)."""
    monkeypatch.delenv("QUICKBOOKS_SCOPES", raising=False)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _authorize_settings() -> Settings:
    """A Settings with the client_id + redirect_uri the authorize-URL builder requires (scope kept
    at the in-code default so the URL reflects the locked decision)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        quickbooks_client_id="qbo-cid",
        quickbooks_redirect_uri="https://api.example.com/v1/integrations/quickbooks/callback",
    )


class TestQuickBooksScopeIsLocked:
    def test_default_scope_is_accounting_only(self, default_settings: Settings) -> None:
        assert default_settings.quickbooks_scopes == ACCOUNTING_ONLY

    def test_default_scope_excludes_payroll_and_payment(self, default_settings: Settings) -> None:
        scopes = default_settings.quickbooks_scopes.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in scopes, f"QBO scope must not include {forbidden!r}"

    def test_scope_list_parses_to_the_single_accounting_scope(self, default_settings: Settings) -> None:
        assert qbo_oauth._scope_list(default_settings) == [ACCOUNTING_ONLY]

    def test_authorize_url_carries_only_the_accounting_scope(self) -> None:
        url = qbo_oauth.build_authorize_url(_authorize_settings(), state="STATE")
        # The scope param round-trips verbatim and contains exactly the accounting scope, nothing more.
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert query["scope"] == [ACCOUNTING_ONLY]
        # Belt-and-suspenders against an encoding surprise: the forbidden surfaces appear nowhere.
        lowered = url.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered
