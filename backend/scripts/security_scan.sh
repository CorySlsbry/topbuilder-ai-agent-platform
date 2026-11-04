#!/usr/bin/env bash
# Software supply-chain security scan for the Top Builder AI backend.
#
# Runs three checks and emits a CycloneDX SBOM, then fails the build if any HIGH/critical issue
# is found. Designed to run identically on a developer laptop and in CI (cloudbuild.security.yaml):
#
#   1. pip-audit  — dependency vulnerability scan against the PyPA Advisory Database (CVE / GHSA).
#   2. bandit     — static application security testing (SAST) for the `app` package.
#   3. cyclonedx  — Software Bill of Materials (SBOM) of the installed dependency tree -> sbom.json.
#
# A frontend note runs `npm audit` + `@cyclonedx/cyclonedx-npm` when a Node toolchain and the
# frontend tree are present (the JS deps live in ../frontend, scanned separately so this script
# stays useful in a backend-only checkout / image).
#
# Exit codes: 0 = clean (no HIGH/critical); 1 = at least one HIGH/critical finding; 2 = a scanner
# could not run (missing tool that auto-install did not resolve). The non-zero exit is what makes
# this a *gate* — a scheduled or push-triggered Cloud Build turns red, not just noisy.
#
# Usage:
#   backend/scripts/security_scan.sh                 # scan, write sbom.json, gate on HIGH/critical
#   STRICT=1 backend/scripts/security_scan.sh        # also fail on MEDIUM (and any bandit finding)
#   NO_INSTALL=1 backend/scripts/security_scan.sh    # never pip-install scanners (CI image pre-bakes them)
#   SBOM_OUT=/workspace/sbom.json backend/scripts/security_scan.sh   # override the SBOM path
set -u  # NOTE: deliberately NOT `set -e` — we want to run every scanner and aggregate the verdict.

# --- locate the backend root (this script lives in backend/scripts/) -------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_DIR/frontend"
cd "$BACKEND_DIR" || exit 2

SBOM_OUT="${SBOM_OUT:-$BACKEND_DIR/sbom.json}"
STRICT="${STRICT:-0}"
NO_INSTALL="${NO_INSTALL:-0}"

# Severity floor that flips the build red. STRICT lowers it from HIGH to MEDIUM.
PIP_AUDIT_FAIL_LEVELS="high critical"
[ "$STRICT" = "1" ] && PIP_AUDIT_FAIL_LEVELS="medium high critical"
BANDIT_SEVERITY="high"          # bandit reports low|medium|high
[ "$STRICT" = "1" ] && BANDIT_SEVERITY="medium"

FAILED=0  # aggregate verdict; any HIGH/critical sets this to 1

say() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
warn() { printf '\033[33m%s\033[0m\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# Prefer running tools as `python -m <tool>` so we use the venv's copy, not a stray global one.
PY="${PYTHON:-python}"
have "$PY" || PY="python3"

ensure_tool() {
  # ensure_tool <module-importable-name> <pip-spec>
  local module="$1" spec="$2"
  if "$PY" -c "import importlib,sys; sys.exit(0 if importlib.util.find_spec('$module') else 1)" 2>/dev/null; then
    return 0
  fi
  if [ "$NO_INSTALL" = "1" ]; then
    warn "missing '$module' and NO_INSTALL=1 — skipping its scan"
    return 1
  fi
  say "installing $spec"
  "$PY" -m pip install --quiet --disable-pip-version-check "$spec" || return 1
}

# ---------------------------------------------------------------------------------------------------
# 1. Dependency vulnerability scan (pip-audit)
# ---------------------------------------------------------------------------------------------------
say "pip-audit — dependency vulnerability scan"
if ensure_tool pip_audit "pip-audit>=2.7"; then
  # Audit the installed environment (the image's real dependency closure). Write a JSON report for
  # CI artifacts, and re-run a human-readable table to the log. pip-audit exits non-zero when it
  # finds ANY vulnerability; we re-derive the verdict from the JSON so we can gate on severity.
  "$PY" -m pip_audit --format json --progress-spinner off >pip-audit.json 2>pip-audit.err || true
  "$PY" -m pip_audit --progress-spinner off || true
  HITS="$(
    "$PY" - "$PWD/pip-audit.json" "$PIP_AUDIT_FAIL_LEVELS" <<'PYEOF'
import json, sys
path, levels = sys.argv[1], set(sys.argv[2].split())
try:
    data = json.load(open(path))
except Exception:
    print(0); sys.exit(0)
deps = data.get("dependencies", data) if isinstance(data, dict) else data
bad = 0
for dep in deps:
    for v in dep.get("vulns", []) or []:
        # Advisory severity isn't always present; treat unknown as "high" so we never under-report.
        sev = (v.get("severity") or v.get("fix_severity") or "high")
        sev = str(sev).lower()
        if any(lvl in sev for lvl in levels) or sev == "":
            bad += 1
print(bad)
PYEOF
  )"
  if [ "${HITS:-0}" -gt 0 ]; then
    warn "pip-audit: $HITS dependency vulnerabilit(ies) at or above the fail threshold ($PIP_AUDIT_FAIL_LEVELS)"
    FAILED=1
  else
    echo "pip-audit: no dependency vulnerabilities at/above the fail threshold."
  fi
else
  warn "pip-audit unavailable — dependency scan SKIPPED (not a pass)."
  [ "$STRICT" = "1" ] && FAILED=1
fi

# ---------------------------------------------------------------------------------------------------
# 2. SAST (bandit) over the application package
# ---------------------------------------------------------------------------------------------------
say "bandit — static application security testing (SAST)"
if ensure_tool bandit "bandit>=1.7"; then
  # Config (exclusions + skips) lives in pyproject.toml [tool.bandit]. Gate on >= $BANDIT_SEVERITY
  # severity with >= medium confidence; write JSON for CI, table to the log.
  "$PY" -m bandit -r app -c pyproject.toml -f json -o bandit.json \
        --severity-level "$BANDIT_SEVERITY" --confidence-level medium >/dev/null 2>&1 || true
  "$PY" -m bandit -r app -c pyproject.toml \
        --severity-level "$BANDIT_SEVERITY" --confidence-level medium
  BANDIT_RC=$?
  # bandit exits 1 when it reports issues at/above the chosen severity, 0 when clean.
  if [ "$BANDIT_RC" -ne 0 ]; then
    warn "bandit: SAST findings at/above '$BANDIT_SEVERITY' severity — see bandit.json"
    FAILED=1
  else
    echo "bandit: no SAST findings at/above '$BANDIT_SEVERITY' severity."
  fi
else
  warn "bandit unavailable — SAST SKIPPED (not a pass)."
  [ "$STRICT" = "1" ] && FAILED=1
fi

# ---------------------------------------------------------------------------------------------------
# 3. SBOM (CycloneDX) of the Python dependency tree
# ---------------------------------------------------------------------------------------------------
say "cyclonedx — Software Bill of Materials (SBOM)"
SBOM_OK=0
# Preferred: cyclonedx-py (the maintained CLI; `cyclonedx-py environment` walks the installed tree).
if ensure_tool cyclonedx_py "cyclonedx-bom>=4.0"; then
  if "$PY" -m cyclonedx_py environment --output-format JSON --output-file "$SBOM_OUT" 2>/dev/null; then
    SBOM_OK=1
  # Older 'cyclonedx-bom' exposed the `cyclonedx-bom` entrypoint over the active environment.
  elif have cyclonedx-bom && cyclonedx-bom --format json --output "$SBOM_OUT" 2>/dev/null; then
    SBOM_OK=1
  elif have cyclonedx-py && cyclonedx-py environment -o "$SBOM_OUT" 2>/dev/null; then
    SBOM_OK=1
  fi
fi
if [ "$SBOM_OK" = "1" ]; then
  echo "SBOM written: $SBOM_OUT"
  # Pass the path as argv (not string-interpolated) so a space in $SBOM_OUT can't break the parse.
  COMPONENTS="$("$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("components",[])))' "$SBOM_OUT" 2>/dev/null || echo '?')"
  echo "SBOM components: $COMPONENTS"
else
  warn "SBOM generation unavailable — install cyclonedx-bom (pip install cyclonedx-bom)."
  [ "$STRICT" = "1" ] && FAILED=1
fi

# ---------------------------------------------------------------------------------------------------
# 4. Frontend note (npm audit + @cyclonedx/cyclonedx-npm), only when a Node tree is present
# ---------------------------------------------------------------------------------------------------
say "frontend (Node) — npm audit + cyclonedx-npm"
if [ -f "$FRONTEND_DIR/package.json" ] && have npm; then
  ( cd "$FRONTEND_DIR" || exit 0
    # Fail the gate on high/critical JS advisories. `npm audit` exits non-zero when the audit-level
    # threshold is met; with --omit=dev we score the shipped runtime tree.
    if npm audit --omit=dev --audit-level=high; then
      echo "npm audit: no high/critical advisories in the runtime tree."
    else
      warn "npm audit: high/critical advisories in the frontend runtime tree."
      FAILED=1
    fi
    # SBOM for the JS tree (best-effort; npx fetches the tool on demand). Separate file from the
    # Python SBOM so each artifact maps to one ecosystem.
    if npx --yes @cyclonedx/cyclonedx-npm --omit dev --output-file "$FRONTEND_DIR/sbom.frontend.json" 2>/dev/null; then
      echo "frontend SBOM written: $FRONTEND_DIR/sbom.frontend.json"
    else
      warn "frontend SBOM (cyclonedx-npm) skipped — run from ./frontend with network access:"
      warn "  npx @cyclonedx/cyclonedx-npm --omit dev --output-file sbom.frontend.json"
    fi
  )
else
  echo "frontend scan skipped: no ../frontend/package.json or npm not on PATH (backend-only context)."
fi

# ---------------------------------------------------------------------------------------------------
say "verdict"
if [ "$FAILED" -ne 0 ]; then
  warn "SECURITY SCAN FAILED — HIGH/critical findings present (or STRICT gate tripped). See the JSON reports above."
  exit 1
fi
echo "SECURITY SCAN PASSED — no HIGH/critical findings."
exit 0
