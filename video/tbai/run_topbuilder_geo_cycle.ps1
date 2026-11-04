# Top Builder AI - GEO flywheel cron runner (invoked by Windows Task Scheduler, twice weekly off-peak).
# Runs ONE fully-automatic cycle headlessly via claude -p. Kill-switch + lock + per-run log.
param(
  # PROOF MODE (harness P3, 2026-08-22): compose the prompt (incl. any RESUME_CONTEXT: block), log its head,
  # run NO agent, write no state, exit 0. Never passed by the dispatcher; proves the prepend without a cycle.
  [switch]$PromptOnly
)
$ErrorActionPreference = "Continue"
$Root    = "C:\Users\you\Downloads\ServiceTitan Agent platform"
$Claude  = "C:\Users\you\.local\bin\claude.exe"
$Prompt  = "C:\Users\you\.claude\skills\geo-flywheel\references\topbuilder-cycle.md"
$Model   = "claude-sonnet-5"   # cost-conscious autonomous default (bumped from retired sonnet-4-6 2026-07-03); claude-opus-4-8 for max reliability
$LogDir  = Join-Path $Root "video\tbai\geo-cron-logs"
$Pause   = Join-Path $Root "video\tbai\GEO_CRON_PAUSED"   # create this file to DISABLE the cron (kill-switch)
$Lock    = Join-Path $LogDir ".running.lock"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
# HARNESS (P0, 2026-08-22): the RUN ID, minted by the runner (workers only read it) - every engine
# script stamps GEO_RUN_ID so the lineage tape, ledgers and catalog join on one key.
$env:GEO_RUN_ID = "top-builder-ai-cycle-" + (Get-Date -Format "yyyyMMdd-HHmm")
# The run START (UTC): the post-cycle judge only judges assets produced at/after it.
$RunStartIso = (Get-Date).ToUniversalTime().ToString("o")
$EngineDir = Join-Path $env:USERPROFILE ".claude\skills\geo-flywheel\references\engine"
. (Join-Path $EngineDir "cycle_agent.ps1")   # PARKED-EXIT CONTINUATION (harness P1 / A4, 2026-08-22)
$Log   = Join-Path $LogDir "cycle_$stamp.log"

function W($m) { "$(Get-Date -Format 'HH:mm:ss')  $m" | Tee-Object -FilePath $Log -Append }
# RESUME FROM STATE (harness P3, 2026-08-22): run-<lane>-cycle.json phase marks (agent, judge) + an end mark in
# `finally`, and a RESUME_CONTEXT: block (<=10 lineage lines - what NOT to repeat) prepended to the prompt when
# the lane's last run never reached its end mark or ended with failed steps. -PromptOnly runs write nothing.
$RunStateOn = -not $PromptOnly
function RS {
  if (-not $RunStateOn) { return }
  & python "$EngineDir\run_state.py" --lane top-builder-ai --target cycle --run-id $env:GEO_RUN_ID --pid $PID @args *>> $Log
}

# Kill-switch: drop a file named GEO_CRON_PAUSED in video\tbai\ to stop all runs.
if (Test-Path $Pause) { W "PAUSED (kill-switch present) - skipping this run."; exit 0 }

# Lock: never overlap (a cycle can run 30-45 min); a stale lock over 8h is ignored.
# The stale window MUST be >= the task's ExecutionTimeLimit, raised to PT8H on 2026-07-27 so an
# overnight render is not killed mid-job. Leaving it at 3h would let a second run start while the
# first was still going, and two cycles writing the same lane's files is worse than a skipped run.
if (Test-Path $Lock) {
  $age = (Get-Date) - (Get-Item $Lock).LastWriteTime
  if ($age.TotalHours -lt 8) { W "LOCKED (a cycle is still running, age $([int]$age.TotalMinutes)m) - skipping."; exit 0 }
  W "stale lock ($([int]$age.TotalHours)h) - overriding."
}
New-Item -ItemType File -Path $Lock -Force | Out-Null

try {
  Set-Location $Root
  W "START Top Builder AI GEO cycle (fully-auto, long-form, model=$Model). Root=$Root"
  if (-not (Test-Path $Claude)) { W "ERROR: claude CLI not found at $Claude"; exit 1 }
  # Unattended auth: a fresh claude -p cannot use the interactive login, so feed it the API key.
  # Max SUBSCRIPTION billing (2026-07-16): strip any API key so headless claude uses the
  # subscription login (claude_local pattern). The old export here billed the metered API.
  Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
  # Headless, unattended: pipe the cycle prompt to claude -p with permissions bypassed (required for cron).
  # ⛔ Cory 2026-07-24: default background-wait ceiling is 600s, but a long-form video render
  # is 30-60 min. On 2026-07-23 the Neuron cycle was TERMINATED at 600s mid-render
  # ("Background tasks still running after 600s; terminating") and every remaining step —
  # cadence recording, asset registration, IndexNow, social post, Slack, vault — died with it.
  # 0 = wait indefinitely; the task ExecutionTimeLimit + the 3h stale-lock remain the outer bounds.
  $env:CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS = "0"
  # RESUME_CONTEXT (P3): only when the lane's last run did not finish cleanly; otherwise nothing is prepended.
  $ResumeCtx = (& python "$EngineDir\run_state.py" --lane top-builder-ai --resume-context 2>$null | Out-String).Trim()
  RS --begin
  $body = ""
  if ($ResumeCtx) {
    W "RESUME_CONTEXT: prepended ($(($ResumeCtx -split "`n").Count) lines) - the lane's last run did not finish cleanly; the brief says what not to repeat."
    $body += $ResumeCtx + "`n`n"
  }
  $body += (Get-Content -Raw $Prompt)
  if ($PromptOnly) {
    W "PROMPT ONLY: agent NOT run, nothing written. Prompt head:"
    foreach ($ln in ($body -split "`n" | Select-Object -First 14)) { W "  | $ln" }
    exit 0
  }
  RS --step agent --status running
  # PARKED-EXIT CONTINUATION (harness P1 / A4, 2026-08-22): cycle_agent.ps1 runs the agent, detects a parked exit
  # (the turn ended on a background render/upload it cannot outlive - AutoAdvisor 10:14 today) and runs ONE bounded
  # continuation with RESUME_CONTEXT (real artifact state, ffprobe-checked) + PRIOR_FAILURES. Returns the last exit.
  $claudeExit = [int](Invoke-CycleAgent -Body $body -Lane "top-builder-ai" -Root $Root -Step "agent" | Select-Object -Last 1)
  # Capture it NOW: every command below (the shorts/long-form gates) overwrites $LASTEXITCODE.
  W "DONE (claude exit $claudeExit). Log: $Log"
  RS --step agent --status $(if ($claudeExit -eq 0) { "done" } else { "failed" }) --note "claude exit $claudeExit"

  # ⛔ SHORTS GATE (Cory 2026-07-26). Same gate as the Neuron runner: claude exiting 0 proves the
  # process ended, not that CYCLE-CORE §12b (short-form) ran. Neuron went 13 days producing no
  # shorts while every cycle reported success. Ask the state on disk.
  # Exit 3 = the cycle published but produced no short, so LastTaskResult stops lying.
  $shortsDebt = Join-Path $env:USERPROFILE ".claude\skills\geo-flywheel\references\engine\shorts_debt.py"
  & python $shortsDebt --lane top-builder-ai --after-cycle --slack *>> $Log
  if ($LASTEXITCODE -eq 3) {
    # ADVISORY, NOT FATAL (2026-08-02). GEO-Shorts-Producer-TopBuilderAI owns shorts and runs on its own
    # dispatch, so failing the FULL cycle for it pages about work this run does not own.
    # The producer's own post-run gate is what fails loudly when a short is truly missed.
    W "short still owed - deferred to GEO-Shorts-Producer-TopBuilderAI (not a cycle failure)."
  }

  # ⛔ LONG-FORM GATE (Cory 2026-07-27). A SHORT IS NOT A SUBSTITUTE FOR THE LONG-FORM. On
  # 2026-07-26 this cycle shipped a 52s reel, logged "finally adopting the fast-reel-as-default
  # pattern", recorded it as the companion and skipped §11 — leaving Top Builder's own YouTube
  # channel with one short and ZERO long-form videos. Shorts debt was clean throughout, so nothing
  # complained. YouTube is a long-form surface; the short is an offcut of it.
  & python $shortsDebt --lane top-builder-ai --kind longform_video --after-cycle --slack *>> $Log
  if ($LASTEXITCODE -eq 3) {
    # ADVISORY, NOT FATAL (2026-08-01). A dedicated long-form producer
    # (GEO-Longform-Producer-TopBuilderAI) now owns this artifact and runs on its own dispatch, so
    # failing the FULL cycle for it pages about work this run was never responsible for - the cycle
    # published its blog and short correctly and still reported rc=3. Keep the debt visible in the
    # log; the producer's own post-run gate is what fails loudly when the long-form is genuinely missed.
    W "long-form still owed - deferred to GEO-Longform-Producer-TopBuilderAI (not a cycle failure)."
  }

  # JUDGE THIS RUN'S BLOG IN CODE (harness P0 / A2, 2026-08-22). Only assets with mtime >= the run
  # start are judged (never blame an older post): TJ ladder or listicle shape, JSON-LD parses, no
  # stale video placeholder. FAIL = exit 3 + the verdict on the lineage tape; NO-RUN = exit 0.
  & python "$EngineDir\judge_run.py" --lane top-builder-ai --since $RunStartIso --kinds blog --assert --run-id $env:GEO_RUN_ID *>> $Log
  $judgeExit = $LASTEXITCODE
  W "judge_run (this run's blog) exit $judgeExit"
  RS --step judge --status $(if ($judgeExit -eq 0) { "done" } else { "failed" }) --note "judge_run exit $judgeExit"

  # WEEKLY-LIMIT IS ITS OWN EXIT (5; parity with run_shorts_cycle.ps1, 2026-08-22). A limit-hit is
  # transient (resets on a known clock), so the dispatcher backs off instead of paging. Only sniff
  # the log when claude itself died, so the phrase appearing in produced CONTENT can never trip it.
  if ($claudeExit -ne 0) {
    $limitHit = Select-String -Path $Log -Pattern "hit your (weekly|usage|5-hour) limit|usage limit reached" -Quiet
    if ($limitHit) { W "LIMIT: the Claude subscription usage limit is exhausted - no work was possible this run."; exit 5 }
  }

  # ⛔ AN AGENT THAT NEVER RAN MUST NOT REPORT SUCCESS (Cory 2026-08-11).
  # This runner logged "DONE (claude exit 1)" and then fell through to exit 0. Proof from this lane's
  # own logs: cycle_2026-08-11_0410.log ran 04:10:03 -> 04:10:10 (SEVEN SECONDS for a job that takes
  # 30-45 min), printed "Failed to authenticate: OAuth session expired and could not be refreshed",
  # and Task Scheduler recorded return code 0. Six days of total outage looked like six days of
  # success; only shorts_debt's "14.64 days dry" gave it away. Exit 4 = the cycle agent failed.
  if ($claudeExit -ne 0) {
    W "FATAL: cycle agent exited $claudeExit - NO WORK WAS DONE. #1 cause: the Claude Max"
    W "       subscription login lapsed. Fix: run 'claude auth login' in a real terminal."
    W "       (Neuron-Auth-Keepalive runs weekly to keep that login from idling out.)"
    exit 4
  }
  if ($judgeExit -eq 3) {
    W "FAILED: judge_run rejected this run's blog (exit 3) - see: python lineage.py --lane top-builder-ai --recent 10"
    exit 3
  }
}
catch { W "EXCEPTION: $($_.Exception.Message)" }
finally {
  Remove-Item $Lock -Force -ErrorAction SilentlyContinue
  RS --end   # END MARK (P3): a step still `running` here did not complete -> failed
}
