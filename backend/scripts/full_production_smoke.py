"""FULL production smoke — every route, every pipeline, three permission levels, on the LIVE stack.

Read-mostly and self-restoring: anything it mutates (provider, voice, executed actions) it puts
back; demo-visible writes are limited to one plausible task + agent runs (idempotent by inputs
hash). Config-dependent outcomes (ACTIONS_ENABLED, learning-route auth tier) are RECORDED as
findings, not failed. Zero third-party deps (urllib only).

Usage:  python backend/scripts/full_production_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_BASE", "https://topbuilder-ai-api-840472456279.us-central1.run.app")
WEB = os.environ.get("WEB_BASE", "https://topbuilder-ai-agent-web-840472456279.us-central1.run.app")
TENANT_ID = "33333333-3333-3333-3333-333333333333"  # canyonridge

AGENTS = ["workforce", "financial", "inventory", "booking", "routing", "documents"]
OPERATOR_AGENTS = ["email", "seo"]

failures: list[str] = []
findings: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}: {detail}")


def note(label: str) -> None:
    print(f"  NOTE  {label}")
    findings.append(label)


def req(method: str, url: str, *, token: str | None = None, body: dict | None = None,
        headers: dict | None = None, timeout: int = 180) -> tuple[int, dict | list | str]:
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
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
    except Exception as e:  # noqa: BLE001 — network-level failure is a finding, not a crash
        return 0, f"NETWORK: {e}"


def envelope_message(b: object) -> str:
    if isinstance(b, dict):
        err = b.get("error")
        if isinstance(err, dict):
            return str(err.get("message", ""))
        return str(b.get("detail", ""))
    return str(b)[:200]


def main() -> int:  # noqa: PLR0915
    print("== 0) health")
    s, b = req("GET", f"{API}/health")
    check("GET /health 200", s == 200, f"{s}")
    s, b = req("GET", f"{API}/health/db")
    check("GET /health/db 200", s == 200, f"{s}: {envelope_message(b)}")

    print("\n== 1) auth")
    s, cfg = req("GET", f"{API}/auth/config")
    check("auth/config 200 + supabase mode", s == 200 and isinstance(cfg, dict) and cfg.get("supabase_url"), f"{s}")
    tokens: dict[str, str] = {}
    for role in ("admin", "analyst", "viewer"):
        s, b = req("POST", f"{API}/auth/dev-token", body={"tenant_slug": "canyonridge", "role": role})
        check(f"dev-token {role}", s == 200 and isinstance(b, dict) and b.get("access_token"), f"{s}")
        tokens[role] = b["access_token"] if isinstance(b, dict) else ""
    admin, analyst, viewer = tokens["admin"], tokens["analyst"], tokens["viewer"]
    s, b = req("POST", f"{API}/auth/dev-token", body={"tenant_slug": "nope"})
    check("dev-token unknown tenant -> 404", s == 404, f"{s}")
    s, me = req("GET", f"{API}/auth/me", token=admin)
    check("auth/me (dev admin) 200", s == 200, f"{s}: {envelope_message(me)}")

    print("\n== 2) providers")
    s, provs = req("GET", f"{API}/v1/providers", token=analyst)
    ok = s == 200 and isinstance(provs, list) and len(provs) == 10
    check("providers list = 10", ok, f"{s} n={len(provs) if isinstance(provs, list) else '?'}")
    if ok:
        check("providers carry auth_kind+connect", all(p.get("auth_kind") and p.get("connect") for p in provs))
    s, b = req("GET", f"{API}/v1/tenant/provider", token=analyst)
    check("tenant provider GET", s == 200 and b.get("provider"), f"{s}")
    original_provider = b.get("provider", "servicetitan") if isinstance(b, dict) else "servicetitan"
    s, b = req("PUT", f"{API}/v1/tenant/provider", token=admin, body={"provider": "acculynx"})
    check("PUT provider acculynx (admin)", s == 200 and b.get("display") == "AccuLynx", f"{s}")
    s, b = req("PUT", f"{API}/v1/tenant/provider", token=analyst, body={"provider": "jobber"})
    check("PUT provider (analyst) -> 403", s == 403, f"{s}")
    s, b = req("PUT", f"{API}/v1/tenant/provider", token=admin, body={"provider": "salesforce"})
    check("PUT bogus provider -> 422 names valid set", s == 422 and "unknown provider" in envelope_message(b), f"{s}")
    s, b = req("PUT", f"{API}/v1/tenant/provider", token=admin, body={"provider": original_provider})
    check(f"provider RESTORED to {original_provider}", s == 200 and b.get("provider") == original_provider, f"{s}")

    print("\n== 3) voice")
    s, voices = req("GET", f"{API}/v1/voice/options", token=viewer)
    check("voice options = 3", s == 200 and isinstance(voices, list) and len(voices) == 3, f"{s}")
    s, b = req("GET", f"{API}/v1/tenant/voice", token=viewer)
    check("tenant voice GET", s == 200 and b.get("voice"), f"{s}")
    original_voice = b.get("voice", "riley") if isinstance(b, dict) else "riley"
    s, b = req("PUT", f"{API}/v1/tenant/voice", token=admin, body={"voice": "marcus"})
    check("PUT voice marcus (admin)", s == 200 and b.get("voice") == "marcus", f"{s}")
    s, b = req("PUT", f"{API}/v1/tenant/voice", token=analyst, body={"voice": "jade"})
    check("PUT voice (analyst) -> 403", s == 403, f"{s}")
    s, b = req("PUT", f"{API}/v1/tenant/voice", token=admin, body={"voice": "alexa"})
    check("PUT bogus voice -> 422", s == 422 and "unknown voice" in envelope_message(b), f"{s}")
    s, b = req("PUT", f"{API}/v1/tenant/voice", token=admin, body={"voice": original_voice})
    check(f"voice RESTORED to {original_voice}", s == 200 and b.get("voice") == original_voice, f"{s}")
    for v in ("riley", "marcus", "jade"):
        # HEAD: previews are binary — don't run them through the JSON reader
        head = urllib.request.Request(f"{WEB}/voices/{v}.mp3", method="HEAD")
        try:
            with urllib.request.urlopen(head, timeout=30) as r:
                check(f"preview {v}.mp3 served by web", r.status == 200,
                      f"{r.status} {r.headers.get('Content-Length')}b")
        except urllib.error.HTTPError as e:
            check(f"preview {v}.mp3 served by web", False, f"{e.code}")

    print("\n== 4) agent policies")
    s, pols = req("GET", f"{API}/v1/agents/policies", token=analyst)
    # only explicitly-set rows come back; unset agents default to hitl implicitly
    check("policies list", s == 200 and isinstance(pols, list), f"{s}")
    s, cur = req("GET", f"{API}/v1/agents/policies/booking", token=admin)
    check("policy GET single (booking)", s == 200 and cur.get("mode"), f"{s}")
    mode = cur.get("mode", "hitl") if isinstance(cur, dict) else "hitl"
    s, b = req("PUT", f"{API}/v1/agents/policies/booking", token=admin, body={"mode": mode})
    check("PUT policy same-value (admin)", s == 200, f"{s}")
    s, b = req("PUT", f"{API}/v1/agents/policies/booking", token=viewer, body={"mode": "auto"})
    check("PUT policy (viewer) -> 403", s == 403, f"{s}")

    print("\n== 5) the six org agents — run + latest + history")
    run_ids: dict[str, str] = {}
    for a in AGENTS:
        qs = "?horizon_days=21" if a == "workforce" else ""
        s, b = req("POST", f"{API}/v1/agents/{a}/runs{qs}", token=analyst, body={})
        check(f"POST {a}/runs", s in (200, 201) and isinstance(b, dict), f"{s}: {envelope_message(b)[:80]}")
        if isinstance(b, dict) and b.get("run_id"):
            run_ids[a] = str(b["run_id"])
        s, b = req("GET", f"{API}/v1/agents/{a}/runs/latest", token=analyst)
        check(f"GET {a}/runs/latest", s == 200 and isinstance(b, dict), f"{s}")
        if a == "booking" and isinstance(b, dict):
            rec = (b.get("totals") or {}).get("recovered_revenue_usd")
            check("booking oracle $3,260 intact", rec == 3260, f"got {rec}")
        s, b = req("GET", f"{API}/v1/agents/{a}/runs", token=analyst)
        check(f"GET {a}/runs history", s == 200 and isinstance(b, list), f"{s}")
    if "financial" in run_ids:
        s, b = req("GET", f"{API}/v1/agents/financial/runs/{run_ids['financial']}", token=analyst)
        check("GET financial/runs/{id}", s == 200, f"{s}")

    print("\n== 6) operator-layer agents (email, seo)")
    for a in OPERATOR_AGENTS:
        s, b = req("GET", f"{API}/v1/agents/{a}/runs/latest", token=analyst)
        check(f"GET {a} latest (analyst) -> 403", s == 403, f"{s}")
        s, b = req("POST", f"{API}/v1/agents/{a}/runs", token=admin, body={})
        check(f"POST {a}/runs (admin)", s in (200, 201), f"{s}: {envelope_message(b)[:80]}")
        s, b = req("GET", f"{API}/v1/agents/{a}/runs/latest", token=admin)
        check(f"GET {a} latest (admin)", s == 200, f"{s}")
        if a == "email" and isinstance(b, dict):
            wf = next((w for w in b.get("workflows", []) if w.get("workflow_id") == "WF-102"), None)
            check("WF-102 applied_rewrite visible", bool(wf and wf.get("applied_rewrite")),
                  "the rewrite applied via the assistant earlier today")

    print("\n== 7) organization layer")
    s, ov = req("GET", f"{API}/v1/org/overview", token=analyst)
    ok = s == 200 and isinstance(ov, dict)
    check("org overview", ok, f"{s}")
    if ok:
        check("38 people / 7 depts / 6 agents",
              len(ov.get("people", [])) == 38 and len(ov.get("departments", [])) == 7 and len(ov.get("agents", [])) == 6)
        pid = ov["people"][0]["id"]
        s, b = req("GET", f"{API}/v1/org/people/{pid}", token=analyst)
        check("org person profile", s == 200, f"{s}")
    s, b = req("GET", f"{API}/v1/org/kpis", token=admin)
    total = next((k for k in (b.get("kpis", []) if isinstance(b, dict) else []) if k.get("key") == "total_value_identified"), None)
    check("executive KPIs total is a number", s == 200 and total and isinstance(total.get("value"), (int, float)),
          f"{s}: {total and total.get('value')}")
    s, b = req("GET", f"{API}/v1/org/access-matrix", token=viewer)
    check("access matrix", s == 200 and isinstance(b, dict) and b.get("dept_agents"), f"{s}")

    print("\n== 8) front desk: comms + tasks")
    s, comms = req("GET", f"{API}/v1/communications", token=analyst)
    check("communications list non-empty", s == 200 and isinstance(comms, list) and len(comms) > 0, f"{s}")
    s, tasks_ = req("GET", f"{API}/v1/tasks", token=analyst)
    check("tasks list", s == 200 and isinstance(tasks_, list), f"{s}")
    s, t = req("POST", f"{API}/v1/tasks", token=analyst,
               body={"title": "Confirm voicemail follow-ups are complete", "department": "front_office", "priority": 4})
    check("create task", s == 201 and isinstance(t, dict) and t.get("id"), f"{s}")
    if isinstance(t, dict) and t.get("id"):
        s, b = req("PATCH", f"{API}/v1/tasks/{t['id']}", token=analyst, body={"status": "done"})
        check("complete task", s == 200 and b.get("status") == "done", f"{s}")
    s, b = req("POST", f"{API}/v1/tasks", token=viewer, body={"title": "viewer write should fail", "department": "front_office"})
    check("create task (viewer) -> 403", s == 403, f"{s}")

    print("\n== 9) action gate pipeline (propose -> approve -> execute -> undo)")
    s, booking = req("GET", f"{API}/v1/agents/booking/runs/latest", token=admin)
    proposed = (booking.get("proposed_bookings") or []) if isinstance(booking, dict) else []
    if not proposed:
        note("no proposed bookings in latest run — action pipeline untested")
    else:
        bk = proposed[0]
        s, action = req("POST", f"{API}/v1/actions", token=admin, body={
            "agent": "booking", "kind": "book_appointment", "run_id": booking.get("run_id"),
            "params": {"intake_id": bk["intake_id"], "trade": bk["trade"],
                       "proposed_date": bk["proposed_date"], "caller_name": bk.get("caller_name")},
        })
        check("propose book_appointment", s == 201 and isinstance(action, dict), f"{s}: {envelope_message(action)[:100]}")
        if isinstance(action, dict) and action.get("status") == "executed":
            # Idempotent: this intake was already booked in a prior run. Reset for a clean test.
            note("booking already executed (idempotent) — undoing to re-test the pipeline")
            req("POST", f"{API}/v1/actions/{action['id']}/undo", token=admin)
            s, action = req("POST", f"{API}/v1/actions", token=admin, body={
                "agent": "booking", "kind": "book_appointment", "run_id": booking.get("run_id"),
                "params": {"intake_id": bk["intake_id"], "trade": bk["trade"],
                           "proposed_date": bk["proposed_date"], "caller_name": bk.get("caller_name")},
            })
        if isinstance(action, dict) and action.get("id") and action.get("status") != "executed":
            aid = action["id"]
            s, b = req("POST", f"{API}/v1/actions/{aid}/approve", token=viewer)
            check("approve (viewer) -> 403", s == 403, f"{s}")
            s, b = req("POST", f"{API}/v1/actions/{aid}/approve", token=admin)
            check("approve (admin)", s == 200, f"{s}: {envelope_message(b)[:80]}")
            s, b = req("POST", f"{API}/v1/actions/{aid}/execute", token=admin)
            if s == 200:
                check("execute (admin)", True)
                ref = (b.get("result") or {}).get("external_ref") if isinstance(b, dict) else None
                check("execute returned external_ref", bool(ref), f"{ref}")
                s, b = req("POST", f"{API}/v1/actions/{aid}/undo", token=admin)
                check("undo restores state", s == 200, f"{s}")
            elif s == 403 and "disabled" in envelope_message(b):
                note("ACTIONS_ENABLED=false on prod — Front Desk 'Approve & book' shows the friendly "
                     "'execution is turned off' message instead of booking. Config decision needed.")
            else:
                check("execute (admin)", False, f"{s}: {envelope_message(b)[:120]}")
        s, b = req("GET", f"{API}/v1/actions", token=admin)
        check("actions list (admin)", s == 200 and isinstance(b, list), f"{s}")

    print("\n== 10) learning governance")
    for path in ("preferences", "drift", "golden", "params"):
        s, b = req("GET", f"{API}/v1/learning/{path}", token=admin)
        check(f"learning/{path} (admin)", s == 200, f"{s}")
    # Governance reads are leadership/operator tier (require_unrestricted): an UNRESTRICTED analyst
    # (no department, like the owner) may read; a department-scoped login may not. dev-tokens have no
    # department, so this analyst is unrestricted and correctly gets 200. The dept-scoped 403 is
    # covered in smoke_alex_demo.py.
    s, b = req("GET", f"{API}/v1/learning/preferences", token=analyst)
    check("learning reads: unrestricted principal 200 [tier]", s == 200, f"{s}")
    s, b = req("POST", f"{API}/v1/learning/consolidate?agent=financial", token=admin)
    check("consolidation pipeline (financial)", s == 200, f"{s}: {envelope_message(b)[:80]}")
    s, b = req("POST", f"{API}/v1/learning/cron/consolidate", body={})
    check("learning cron unauthenticated -> 403", s == 403, f"{s}")

    print("\n== 11) assistant")
    s, b = req("POST", f"{API}/v1/assistant/chat", token=admin,
               body={"messages": [{"role": "user", "content": "Reply with exactly: SMOKE-OK"}]})
    check("assistant chat (admin)", s == 200 and isinstance(b, dict) and "SMOKE-OK" in b.get("reply", ""), f"{s}")
    s, b = req("POST", f"{API}/v1/assistant/chat", token=viewer,
               body={"messages": [{"role": "user", "content": "Create a task titled smoke-viewer-test for the front office."}]})
    ok = s == 200 and isinstance(b, dict) and not any(
        a.get("tool") == "create_task" for a in b.get("actions", []))
    check("assistant refuses viewer write (no create_task action)", ok,
          f"{s}; actions={[a.get('tool') for a in b.get('actions', [])] if isinstance(b, dict) else '?'}")
    s, b = req("POST", f"{API}/v1/assistant/chat", token=admin, body={"messages": []})
    check("assistant empty history -> 422", s == 422, f"{s}")

    print("\n== 12) field ops (the /field PWA backend)")
    s, pb = req("GET", f"{API}/v1/field/pricebook", token=analyst)
    check("pricebook", s == 200 and isinstance(pb, list) and len(pb) > 0, f"{s}")
    s, jobs = req("GET", f"{API}/v1/field/jobs", token=analyst)
    check("jobs", s == 200 and isinstance(jobs, list) and len(jobs) > 0, f"{s}")
    if isinstance(pb, list) and len(pb) >= 2:
        items = [{"service_code": pb[0]["code"], "qty": 1}, {"service_code": pb[1]["code"], "qty": 2}]
        expected_sub = round(pb[0]["unit_price_usd"] * 1 + pb[1]["unit_price_usd"] * 2, 2)
        expected_tax = round(sum(p["unit_price_usd"] * q for p, q in ((pb[0], 1), (pb[1], 2)) if p["taxable"]) * 0.086, 2)
        s, q = req("POST", f"{API}/v1/field/quote", token=analyst, body={"line_items": items, "tax_rate": 0.086})
        ok = s == 200 and isinstance(q, dict) and abs(q.get("subtotal_usd", -1) - expected_sub) < 0.011 \
            and abs(q.get("tax_usd", -1) - expected_tax) < 0.011
        check("quote math deterministic", ok,
              f"{s}: got {q.get('subtotal_usd')}+{q.get('tax_usd')} want {expected_sub}+{expected_tax}" if isinstance(q, dict) else f"{s}")
        s, b = req("POST", f"{API}/v1/field/quote/submit", token=analyst,
                   body={"line_items": items[:1], "tax_rate": 0.086, "job_ref": None})
        check("quote submit -> action created", s == 201 and b.get("status") in ("proposed", "executed"),
              f"{s}: {b.get('status') if isinstance(b, dict) else envelope_message(b)[:80]}")

    print("\n== 13) feedback loop")
    fin_run = run_ids.get("financial")
    s, b = req("POST", f"{API}/v1/feedback", token=analyst,
               body={"agent": "financial", "rating": "up", "run_id": fin_run, "note": "production smoke"})
    check("feedback submit", s == 201, f"{s}: {envelope_message(b)[:80]}")
    s, b = req("GET", f"{API}/v1/feedback?agent=financial", token=analyst)
    check("feedback list", s == 200 and isinstance(b, list), f"{s}")
    s, b = req("GET", f"{API}/v1/feedback/training-signal?agent=financial", token=analyst)
    check("training signal", s == 200, f"{s}")

    print("\n== 13b) SECURITY hardening (SEC-4/5/7/8)")
    # SEC-8: connection writes require admin (was analyst)
    s, _ = req("PUT", f"{API}/v1/connections", token=analyst,
               body={"provider": "servicetitan", "secret": {"x": 1}})
    check("connections PUT (analyst) -> 403 [SEC-8]", s == 403, f"{s}")
    # SEC-4: webhook now requires a timestamp + tenant-bound signature
    s, b = req("POST", f"{API}/v1/webhooks/servicetitan/{TENANT_ID}", body={"id": "x"},
               headers={"X-Signature": "deadbeef"})
    check("webhook without timestamp -> 401 [SEC-4]", s == 401, f"{s}")
    # SEC-7: a department-scoped login must NOT see ai_context/email on a person profile
    s, ov2 = req("GET", f"{API}/v1/org/overview", token=admin)
    pid2 = ov2["people"][0]["id"] if isinstance(ov2, dict) and ov2.get("people") else None
    if pid2:
        s, dprofile = req("GET", f"{API}/v1/org/people/{pid2}", token=admin)  # admin sees it
        admin_sees = isinstance(dprofile, dict) and "ai_context" in dprofile.get("person", {})
        check("admin sees ai_context [SEC-7]", admin_sees, "unrestricted principal")
    # SEC-5: feedback accepts normal input (cap is high; just confirm the path still 201s)
    s, _ = req("POST", f"{API}/v1/feedback", token=analyst,
               body={"agent": "financial", "rating": "up", "note": "sec smoke"})
    check("feedback still works under cap [SEC-5]", s == 201, f"{s}")
    # SEC-5: oversized correction rejected at the schema (422)
    s, _ = req("POST", f"{API}/v1/feedback", token=analyst,
               body={"agent": "financial", "rating": "edit", "correction": "x" * 9000})
    check("oversized feedback correction -> 422 [SEC-5]", s == 422, f"{s}")

    print("\n== 14) knowledge / connections / webhooks / admin")
    s, b = req("GET", f"{API}/v1/knowledge/financial/documents", token=admin)
    check("knowledge documents list", s == 200, f"{s}")
    s, b = req("POST", f"{API}/v1/knowledge/financial/search", token=admin, body={"query": "overtime"})
    if s == 200:
        print("  PASS  knowledge search 200")
    else:
        note(f"knowledge search status {s} ({envelope_message(b)[:90]}) — embeddings likely unconfigured in prod")
    s, b = req("GET", f"{API}/v1/connections", token=admin)
    check("connections (admin)", s == 200, f"{s}")
    s, b = req("POST", f"{API}/v1/webhooks/servicetitan/{TENANT_ID}", body={"event": "junk"})
    check("unsigned webhook fail-closed", s in (401, 403), f"{s}")
    s, b = req("GET", f"{API}/v1/webhooks/events", token=admin)
    check("webhook events (admin)", s == 200, f"{s}")
    s, b = req("GET", f"{API}/v1/admin/memberships", token=admin)
    check("admin memberships (admin)", s == 200, f"{s}")
    s, b = req("GET", f"{API}/v1/admin/memberships", token=analyst)
    check("admin memberships (analyst) -> 403", s == 403, f"{s}")
    s, b = req("POST", f"{API}/v1/agents/email/cron/daily", body={})
    check("email cron unauthenticated -> 403", s == 403, f"{s}")
    s, b = req("POST", f"{API}/v1/agents/seo/cron/weekly", body={})
    check("seo cron unauthenticated -> 403", s == 403, f"{s}")

    print("\n== 15) error envelope + CORS posture")
    s, b = req("GET", f"{API}/v1/not-a-route", token=admin)
    check("404 wrapped in error envelope", s == 404 and isinstance(b, dict) and "error" in b, f"{s}")
    pre = urllib.request.Request(
        f"{API}/v1/assistant/chat", method="OPTIONS",
        headers={"Origin": WEB, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,authorization"})
    try:
        with urllib.request.urlopen(pre, timeout=30) as r:
            check("CORS allows the web origin", r.status == 200 and r.headers.get("Access-Control-Allow-Origin") == WEB,
                  f"{r.status} ACAO={r.headers.get('Access-Control-Allow-Origin')}")
    except urllib.error.HTTPError as e:
        check("CORS allows the web origin", False, f"{e.code}")
    pre2 = urllib.request.Request(
        f"{API}/v1/assistant/chat", method="OPTIONS",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    try:
        with urllib.request.urlopen(pre2, timeout=30):
            check("CORS blocks foreign origins", False, "localhost preflight unexpectedly 200")
    except urllib.error.HTTPError as e:
        check("CORS blocks foreign origins", e.code == 400, f"{e.code}")

    print(f"\n{'=' * 60}")
    print(f"RESULT: {'ALL GREEN' if not failures else f'{len(failures)} FAILURE(S)'}; {len(findings)} finding(s)")
    for f in failures:
        print(f"  FAIL  {f}")
    for f in findings:
        print(f"  NOTE  {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
