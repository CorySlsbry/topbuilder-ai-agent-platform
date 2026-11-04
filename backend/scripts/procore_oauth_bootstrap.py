"""Procore OAuth bootstrap + read-probe (Development Sandbox).

Gets Top Builder AI's first Procore connection ONLINE against the developer sandbox
(company 4285693, https://sandbox.procore.com), then probes the read endpoints and dumps the
REAL field shapes so the mappers in `app/integrations/construction/mappers.py` are filled from
verified data — never guessed (ADR-0003 figure firewall).

What it does, in order:
  1. Prints the authorize URL (redirect to http://localhost, which the sandbox already allows). Open
     it in a browser signed in to the sandbox, click Allow; the browser fails to load localhost but the
     ?code=... is in the address bar — copy it. (Use --redirect-uri urn:ietf:wg:oauth:2.0:oob to have
     Procore print the code on-page instead, if oob is registered on the sandbox redirect URI.)
  2. Exchanges that code at /oauth/token for an access + refresh token (grant_type=authorization_code).
  3. GET /rest/v1.0/me + /rest/v1.0/companies to confirm identity and the company id.
  4. Probes the read surface (projects -> rfis/submittals/daily-logs, vendors, prime-contracts,
     commitments) and prints status + row count + the first row's keys + a truncated sample, so the
     exact field names + units are visible.
  5. Prints the refresh_token + the env block to set. STORE the refresh token in Secret Manager /
     the AES-256-GCM vault — it is a live credential; do not commit it.

Secrets are READ FROM ENV, never hardcoded:
    PROCORE_CLIENT_ID, PROCORE_CLIENT_SECRET   (the SANDBOX OAuth credentials)

Usage (from backend/, with the sandbox creds exported):
    python scripts/procore_oauth_bootstrap.py                       # full flow, prompts for the code
    python scripts/procore_oauth_bootstrap.py --code <CODE>         # non-interactive code exchange
    python scripts/procore_oauth_bootstrap.py --refresh-token <RT>  # skip auth, re-probe with a token

All API calls are read-only GETs. Exit 0 = a token was obtained (and the probe ran).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx

DEFAULT_HOST = "https://sandbox.procore.com"  # dev sandbox: oauth + api share this host
DEFAULT_COMPANY_ID = "4285693"  # the sandbox company tied to app 16a085d8
# The sandbox app already allows http://localhost — after Allow, Procore redirects to
# http://localhost/?code=...; the browser can't load it but the code is in the address bar. Pass
# --redirect-uri urn:ietf:wg:oauth:2.0:oob instead if you'd rather Procore print the code on-page
# (that requires oob to be registered on the SANDBOX redirect URI, not just production).
DEFAULT_REDIRECT_URI = "http://localhost"
_TRUNC = 1200  # cap each sample dump so the output stays readable


def _client_creds() -> tuple[str, str]:
    cid = os.environ.get("PROCORE_CLIENT_ID")
    secret = os.environ.get("PROCORE_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit(
            "Set PROCORE_CLIENT_ID and PROCORE_CLIENT_SECRET (the SANDBOX OAuth credentials from the "
            "Procore developer app) before running."
        )
    return cid, secret


def _authorize_url(host: str, client_id: str, redirect_uri: str) -> str:
    return (
        f"{host}/oauth/authorize?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
    )


async def _exchange_code(
    host: str, client_id: str, secret: str, code: str, redirect_uri: str
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"{host}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": secret,
                "code": code.strip(),
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        sys.exit(f"Token exchange failed [{resp.status_code}]: {resp.text}")
    return resp.json()


async def _refresh(host: str, client_id: str, secret: str, refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"{host}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        sys.exit(f"Refresh failed [{resp.status_code}]: {resp.text}")
    return resp.json()


def _shape(rows: Any) -> str:
    """A compact view of a response: row count + first row's keys + a truncated sample."""
    if isinstance(rows, dict):
        # Some endpoints wrap the list, others return the object directly.
        inner = rows.get("data") if "data" in rows else None
        if isinstance(inner, list):
            rows = inner
        else:
            keys = ", ".join(sorted(rows.keys()))
            return f"object — keys: {keys}\n    {json.dumps(rows)[:_TRUNC]}"
    if not isinstance(rows, list):
        return f"scalar/other: {json.dumps(rows)[:_TRUNC]}"
    if not rows:
        return "0 rows"
    first = rows[0]
    keys = ", ".join(sorted(first.keys())) if isinstance(first, dict) else "(non-dict rows)"
    return f"{len(rows)} rows — first-row keys: {keys}\n    {json.dumps(first)[:_TRUNC]}"


async def _get(c: httpx.AsyncClient, label: str, path: str, *, company_id: str, params: dict | None = None):
    headers = {"Procore-Company-Id": company_id, "Accept": "application/json"}
    try:
        resp = await c.get(path, params=params or {}, headers=headers)
    except Exception as exc:  # noqa: BLE001 — probe must never abort on one bad endpoint
        print(f"\n[{label}] {path}\n    ERROR: {exc}")
        return None
    print(f"\n[{label}] GET {path}  ->  {resp.status_code}")
    if resp.status_code != 200:
        print(f"    {resp.text[:300]}")
        return None
    body = resp.json()
    print(f"    {_shape(body)}")
    return body.get("data") if isinstance(body, dict) and "data" in body else body


async def _probe(host: str, token: str, company_id: str) -> None:
    print("\n================ READ PROBE (real sandbox field shapes) ================")
    async with httpx.AsyncClient(
        base_url=host, timeout=60, headers={"Authorization": f"Bearer {token}"}
    ) as c:
        await _get(c, "me", "/rest/v1.0/me", company_id=company_id)
        await _get(c, "companies", "/rest/v1.0/companies", company_id=company_id)
        # projects power the jobs domain; v1.1 is current, fall back to v1.0.
        projects = await _get(
            c, "projects(v1.1)", "/rest/v1.1/projects", company_id=company_id,
            params={"company_id": company_id, "per_page": 5},
        )
        if not projects:
            projects = await _get(
                c, "projects(v1.0)", "/rest/v1.0/projects", company_id=company_id,
                params={"company_id": company_id, "per_page": 5},
            )
        await _get(
            c, "vendors", "/rest/v1.0/vendors", company_id=company_id,
            params={"company_id": company_id, "per_page": 5},
        )
        pid = None
        if isinstance(projects, list) and projects and isinstance(projects[0], dict):
            pid = projects[0].get("id")
        if pid:
            print(f"\n--- per-project reads (project_id={pid}) ---")
            await _get(c, "rfis", f"/rest/v1.0/projects/{pid}/rfis", company_id=company_id,
                       params={"per_page": 5})
            await _get(c, "submittals", f"/rest/v1.1/projects/{pid}/submittals", company_id=company_id,
                       params={"per_page": 5})
            await _get(c, "prime_contracts", "/rest/v1.0/prime_contract", company_id=company_id,
                       params={"project_id": pid})
            await _get(c, "commitments", f"/rest/v1.0/projects/{pid}/commitments", company_id=company_id,
                       params={"per_page": 5})
        else:
            print("\n(no projects returned — seed the sandbox or check the granted permission template)")


async def main() -> int:
    ap = argparse.ArgumentParser(description="Procore sandbox OAuth bootstrap + read probe")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    ap.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI,
                    help="must be registered on the SANDBOX redirect URI (default http://localhost)")
    ap.add_argument("--code", help="authorization code (skip the interactive prompt)")
    ap.add_argument("--refresh-token", help="skip auth: refresh this token and probe")
    args = ap.parse_args()

    client_id, secret = _client_creds()

    if args.refresh_token:
        tok = await _refresh(args.host, client_id, secret, args.refresh_token)
    else:
        code = args.code
        if not code:
            print("1) Open this URL in a browser signed in to the sandbox, then click Allow:\n")
            print("   " + _authorize_url(args.host, client_id, args.redirect_uri) + "\n")
            if args.redirect_uri == "http://localhost":
                print("   The browser will fail to load http://localhost/?code=... — that's expected.")
                print("   Copy the value after `code=` (up to any `&`) from the address bar.\n")
            else:
                print("   Procore will display the authorization code on the page; copy it.\n")
            code = input("2) Paste the authorization code here: ").strip()
        tok = await _exchange_code(args.host, client_id, secret, code, args.redirect_uri)

    access = tok["access_token"]
    refresh = tok.get("refresh_token", "")
    print("\n✅ Token obtained.")
    print(f"    expires_in: {tok.get('expires_in')}  ")
    print(f"    refresh_token: {refresh}")
    print(
        "\n→ STORE the refresh token as a secret (Secret Manager / the AES-256-GCM vault). Then set live mode:\n"
        f"    PROCORE_MODE=live\n"
        f"    PROCORE_CLIENT_ID / PROCORE_CLIENT_SECRET = the sandbox creds\n"
        f"    PROCORE_REFRESH_TOKEN = <the value above>\n"
        f"    PROCORE_COMPANY_ID = {args.company_id}\n"
        f"    PROCORE_BASE_URL = {args.host}\n"
        f"    PROCORE_AUTH_URL = {args.host}/oauth/token\n"
    )

    await _probe(args.host, access, args.company_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
