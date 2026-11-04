"""Live E2E smoke for the Alex demo: 4 Supabase logins -> /auth/me shape -> org overview ->
executive KPIs (alex 200, dept logins 403) -> allowed agent 200 -> disallowed agent 403.
Zero third-party deps (urllib only).

Usage (passwords via env, never hardcoded):
  API_BASE=https://... ALEX_PW=... DISPATCH_PW=... FRONTDESK_PW=... FINANCE_PW=... \
    python backend/scripts/smoke_alex_demo.py [--prewarm]

--prewarm: as alex (analyst, unrestricted), POST a run for all 6 agents first so /runs/latest is 200.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_BASE", "https://topbuilder-ai-api-840472456279.us-central1.run.app")
AGENTS = ["workforce", "financial", "inventory", "booking", "routing", "documents"]

LOGINS = [
    # (env var, email, expected department, expected allowed agents or None, one allowed, one blocked)
    ("ALEX_PW", "person1@example.com", None, None, "financial", None),
    ("DISPATCH_PW", "dispatch.demo@topbuilderai.com", "dispatch", {"routing"}, "routing", "financial"),
    ("FRONTDESK_PW", "frontdesk.demo@topbuilderai.com", "front_office", {"booking", "documents"}, "booking", "financial"),
    ("FINANCE_PW", "finance.demo@topbuilderai.com", "finance", {"financial", "documents"}, "financial", "routing"),
]

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}: {detail}")


def req(method: str, url: str, *, token: str | None = None, body: dict | None = None,
        headers: dict | None = None) -> tuple[int, dict | list | str]:
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> int:
    prewarm = "--prewarm" in sys.argv

    status, cfg = req("GET", f"{API}/auth/config")
    if status != 200 or not isinstance(cfg, dict) or not cfg.get("supabase_url"):
        print(f"FATAL: /auth/config unusable ({status}): {cfg}")
        return 1
    sb_url, anon = cfg["supabase_url"].rstrip("/"), cfg["supabase_anon_key"]

    def login(email: str, password: str) -> str | None:
        status, body = req(
            "POST", f"{sb_url}/auth/v1/token?grant_type=password",
            body={"email": email, "password": password}, headers={"apikey": anon},
        )
        if status != 200 or not isinstance(body, dict):
            print(f"  FAIL  login {email} ({status}): {str(body)[:200]}")
            failures.append(f"login {email}")
            return None
        return body["access_token"]

    tokens: dict[str, str] = {}
    for env_var, email, *_ in LOGINS:
        pw = os.environ.get(env_var)
        if not pw:
            print(f"FATAL: {env_var} not set")
            return 1
        print(f"\n== {email}")
        tok = login(email, pw)
        if tok:
            tokens[email] = tok
            print(f"  PASS  login")

    alex_tok = tokens.get("person1@example.com")
    if alex_tok:
        # First overview read seeds the canyonridge roster (seed-on-read) — must happen before
        # the /auth/me person assertions below can resolve membership.person_id -> org_people.
        status, _ = req("GET", f"{API}/v1/org/overview", token=alex_tok)
        print(f"\n== seed-on-read overview as alex: {status}")

    if prewarm and alex_tok:
        print("\n== prewarm: running all 6 agents as alex")
        for a in AGENTS:
            qs = "?horizon_days=21" if a == "workforce" else ""
            status, _ = req("POST", f"{API}/v1/agents/{a}/runs{qs}", token=alex_tok, body={})
            check(f"prewarm {a}", status in (200, 201), f"status {status}")

    for env_var, email, dept, allowed, ok_agent, blocked_agent in LOGINS:
        tok = tokens.get(email)
        if not tok:
            continue
        print(f"\n== checks: {email}")

        status, me = req("GET", f"{API}/auth/me", token=tok)
        check("auth/me 200", status == 200, f"status {status}")
        if isinstance(me, dict):
            check("department", me.get("department") == dept, f"got {me.get('department')!r}")
            got_allowed = me.get("allowed_agents")
            if allowed is None:
                check("allowed_agents is null (all)", got_allowed is None, f"got {got_allowed!r}")
            else:
                check("allowed_agents exact", isinstance(got_allowed, list) and set(got_allowed) == allowed,
                      f"got {got_allowed!r}")
            check("person linked", isinstance(me.get("person"), dict) and me["person"].get("full_name"),
                  f"got {me.get('person')!r}")
            sections = me.get("allowed_sections")
            if dept is not None:
                check("'organization' in sections", isinstance(sections, list) and "organization" in sections,
                      f"got {sections!r}")

        status, ov = req("GET", f"{API}/v1/org/overview", token=tok)
        check("org overview 200 (wayfinding for all)", status == 200, f"status {status}")
        if isinstance(ov, dict):
            n_people = len(ov.get("people", []))
            check("38 people", n_people == 38, f"got {n_people}")
            check("7 departments", len(ov.get("departments", [])) == 7, f"got {len(ov.get('departments', []))}")
            check("6 agents", len(ov.get("agents", [])) == 6, f"got {len(ov.get('agents', []))}")

        # Executive KPI view: unrestricted logins get the rollup; dept-scoped logins get a 403.
        status, kb = req("GET", f"{API}/v1/org/kpis", token=tok)
        if dept is None:
            check("executive /v1/org/kpis 200", status == 200, f"status {status}")
            if isinstance(kb, dict):
                total = next(
                    (k for k in kb.get("kpis", []) if k.get("key") == "total_value_identified"), None
                )
                is_number = (total is not None
                             and isinstance(total.get("value"), (int, float))
                             and not isinstance(total.get("value"), bool))
                check("total_value_identified is a number", is_number, f"got {total!r}")
        else:
            check("executive /v1/org/kpis -> 403", status == 403, f"status {status}: {str(kb)[:120]}")
            # The deployed API wraps errors as {"error": {"message": ...}} — search the whole body.
            check("403 names the executive view", "executive view" in json.dumps(kb) if isinstance(kb, (dict, list)) else "executive view" in str(kb), f"got {str(kb)[:160]!r}")

        status, _ = req("GET", f"{API}/v1/agents/{ok_agent}/runs/latest", token=tok)
        check(f"allowed agent {ok_agent} reachable", status == 200, f"status {status}")

        if blocked_agent:
            status, body = req("GET", f"{API}/v1/agents/{blocked_agent}/runs/latest", token=tok)
            check(f"blocked agent {blocked_agent} -> 403", status == 403, f"status {status}: {str(body)[:120]}")

        # Governance reads are leadership/operator tier: Alex (unrestricted) may read; the three
        # department-scoped logins may NOT (SEC: require_unrestricted on /v1/learning/*).
        status, lb = req("GET", f"{API}/v1/learning/preferences", token=tok)
        if dept is None:
            check("learning reads: Alex (unrestricted) 200", status == 200, f"status {status}")
        else:
            check(f"learning reads: dept '{dept}' -> 403", status == 403, f"status {status}")

    print(f"\n{'ALL GREEN' if not failures else f'{len(failures)} FAILURE(S)'}")
    for f in failures:
        print(f"  - {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
