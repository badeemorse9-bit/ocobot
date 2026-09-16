# AGENT STATE
> Last updated by: continuity-policy pass | Repository baseline: `67ec2d7`

---

## Project Goal
Build a Binance Spot OCO safe editor that lets a user monitor, edit, and atomically replace ONE selected OCO order by `orderListId` — without freezing the UI on mode switches or provider teardown.

---

## Stack
| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| UI Framework | PySide6 (Qt6) |
| HTTP client | httpx (async) |
| WebSocket client | websockets |
| Test runner | pytest |
| Exchange integration | Binance Spot REST + WebSocket (paper + testnet + live) |

---

## What's Working
- R1 stop token exists and is intended to make monitor shutdown cooperative.
- R2 rollover rehydration exists and is covered by unit tests from the prior implementation work.
- R3 symbol guard exists at both the coordinator and UI layers.
- R4 provider-close drain was implemented in commit `67ec2d7` in `src/ocobot/ui/main_window.py`.
- Dynamic Monitor UI and Paper provider are in place.
- Testnet adapter is wired in; credentials are read from environment variables / `.env` and are not hardcoded.
- LIVE mode remains gated.

### Test-count note
`NEXT.json` records **62 passed** as the current verified offline baseline immediately after the R4 handoff. Earlier documentation reported 67, creating a conflicting/stale count. Do not treat either number as newly verified until the appropriate test run is performed. The next executor must record the actual result.

---

## Current Risks / Unverified Gates
- **R4 verification:** the provider-close drain implementation exists, but the repository has not yet established a fresh test result proving its intended timing/lifecycle behavior after commit `67ec2d7`.
- **Gate 1 — Testnet acceptance:** blocked on real Binance Testnet credentials. `tests/test_testnet_acceptance.py` is not a CI gate and must be run manually with valid credentials.
- **Gate 2 — human safety review:** not done. LIVE mode must remain disabled until the human review is completed.
- Do not enable LIVE merely because offline tests are green.

---

## Full Engineering Plan
The plan was established by the architecture/planning pass and is the default execution direction for Opus.

### R4 — Provider-close race
Implemented in `67ec2d7`. The code captures the in-flight `ThreadPoolExecutor` future before clearing the monitor reference, signals the monitor stop, performs a bounded drain, then closes the old provider.

**Stage closure rule:** R4 is NOT considered complete merely because the code change exists. It must be verified against its acceptance criteria and regression coverage. If verification exposes a correctness or lifecycle defect, remain on R4, fix it, and verify again before advancing.

### R5 — Cooperative stop regression (CURRENT TASK)
- Add the targeted regression test described by `NEXT.json`.
- Verify the current `main_window.py` behavior relevant to the monitor future.
- Acceptance: the new regression test passes and the full offline suite remains green.

### Gate 1 — Testnet acceptance
- Run `tests/test_testnet_acceptance.py` with real Binance Testnet credentials.
- Do not modify the acceptance test merely to make it pass.

### Gate 2 — Human safety review
- Human review of the LIVE order submission path.
- LIVE remains disabled until this review is explicitly completed.

### Final — LIVE enablement
Only after Gate 1 and Gate 2 are complete: review the live path, add/retain explicit confirmation, and then consider enabling LIVE.

### Final regression
Run the strongest appropriate final test suite, including Testnet acceptance when credentials and environment are available.

---

## Executor Operating Model

### Architect vs Executor
The project uses a deliberate two-role workflow:

**Architect (Sonnet):** may perform broad repository analysis, establish or revise the engineering architecture, identify risks, define milestones, and write the persistent engineering plan.

**Executor (Opus):** consumes that plan and turns it into verified repository progress. Opus should NOT spend the session rebuilding the project analysis from scratch when a current plan and state already exist.

Opus may challenge or adjust the plan only when implementation evidence reveals a concrete technical, safety, or correctness reason. Any such change must be recorded in `AGENT_STATE.md`. This does NOT authorize Opus to replace the architecture/planning pass or create a new high-level plan during ordinary execution.

### Fast context recovery — mandatory
At session start:

1. Read `NEXT.json`.
2. Read the relevant current sections of `AGENT_STATE.md`.
3. Check `git status` and current `HEAD`.
4. Inspect only the files directly required by the current task.
5. Start productive implementation as soon as sufficient context is available.

Do NOT perform a broad repository rescan merely to become comfortable with the codebase.
Do NOT consume the session on analysis, planning, or documentation when the current task is already sufficiently specified to implement.
Do NOT recreate the Architect's work unless a concrete implementation issue makes a targeted review necessary.

### Execution rule
The plan can be large; execution should be incremental and checkpointed.

For the current task:

1. Understand the minimum context needed.
2. Implement the task.
3. Run the appropriate focused/full offline test command at the required checkpoint.
4. Verify the stage acceptance criteria before advancing.
5. If acceptance fails, keep the same stage active and fix the defect; do not advance `NEXT.json`.
6. Update `AGENT_STATE.md` and `NEXT.json` with the real result.
7. Commit a coherent checkpoint.
8. Continue to the next planned task only after the current stage is actually closed.

Do not let a session reach its limit with substantial work that exists only in transient reasoning. Persist meaningful progress while working.

### Stage exit gate — NO SKIPPING
A stage is CLOSED only when all of the following are true:

1. The intended implementation is present.
2. The relevant test/check has actually been run.
3. The stage's acceptance criteria are satisfied.
4. No known unresolved correctness, safety, or lifecycle defect remains for that stage.
5. `AGENT_STATE.md` records the evidence and current result.

"Implemented" does not mean "verified".
"Tested" does not automatically mean "safe".
"NEXT.json says the next task" does not override an unresolved defect in the current stage.

If a defect is found during implementation or targeted closure review, fix the defect within the current stage and re-run the relevant verification. Do not simply move the defect into a later task unless the current architecture explicitly requires that sequencing.

### No unnecessary rereading
Before advancing a stage, perform a TARGETED closure review of the changed code, relevant tests, and acceptance criteria only.

Do NOT re-audit the entire repository between stages.
Do NOT reopen unrelated files merely to re-understand the project.
Do NOT repeat expensive full-suite runs without a concrete reason.

The goal is to catch real defects without wasting the executor's context budget on broad rereading.

### Test discipline
Use focused tests while iterating when appropriate; perform the required suite once at the checkpoint.
Never report a test result that was not actually run.
If a test fails because of the current change, fix the issue before closing the stage.

### Scope discipline
Keep the project focused on Binance Spot OCO order management/editing.
Preserve exact order isolation by `orderListId`.
Do not introduce unrelated market-order trading functionality.
Do not modify unrelated files merely to improve style.

### Safety discipline
Treat cancel/create replacement logic, asynchronous lifecycle, stale results, provider teardown, order identity, and LIVE/Testnet boundaries as safety-critical.
Never trade safety for session completion speed.
Never silently enable LIVE behavior.

---

## Continuous Checkpointing
`AGENT_STATE.md` is a live engineering handoff, not an end-of-session diary.

Update it at meaningful milestones, especially after:
- completing a substantial implementation step,
- making an important architectural decision,
- discovering a blocker or risk,
- reaching a stable test checkpoint,
- or before a potentially interruptible long operation.

The checkpoint must preserve the actual state of the repository, not an intended future state.

At minimum keep these facts current:
- current objective
- current engineering plan
- completed work
- in-progress work
- verified results
- unverified results
- risks/blockers
- decisions
- exact next continuation point

---

## Git Hygiene
- Do not reset, discard, or rewrite unrelated work.
- Do not commit credentials, generated artifacts, or scratch/debug files.
- Before commit, inspect the diff and ensure only intended files are staged.
- Keep commits coherent and easy for the next executor to understand.
- The repository's actual Git state takes precedence over stale prose in handoff documents.
