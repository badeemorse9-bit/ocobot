# AGENT STATE
> Last updated by: R5 closure checkpoint | Repository baseline: `80dcdb7` (+ working-tree add: tests/test_stop_token.py, uncommitted)

## Project Goal
Binance Spot OCO safe editor: monitor, edit, and atomically replace ONE selected OCO order by `orderListId`, with safe async lifecycle and no UI freeze on provider teardown.

## Stack
Python 3.11, PySide6/Qt6, httpx, websockets, pytest. Exchange integration: Binance Spot REST/WebSocket with Paper + Testnet + gated LIVE.

## Verified Current State
- R1 cooperative monitor stop token implemented.
- R2 rollover rehydration implemented and unit-covered.
- R3 symbol guard implemented at coordinator + UI layers.
- R4 provider-close race fix implemented in `src/ocobot/ui/main_window.py` and committed in `80dcdb7`.
- R4 behavior: capture the in-flight `ThreadPoolExecutor` future before clearing it; signal cooperative stop; wait up to the bounded timeout; if still running, defer old-provider teardown to future completion so `old.close()` cannot overlap the running task.
- R4 regression coverage: `tests/test_switch_mode_provider_close.py`.
- Targeted R4 regression test: **4 passed** in 1.14s.
- Full offline suite: **66 passed** in 7.30s, 0 failures, 0 errors.
- `git diff --check`: clean before commit.
- LIVE remains gated.
- R5 cooperative stop-token regression added in `tests/test_stop_token.py`: 4 tests (2 parametrized cases x 2). Verifies a signalled cooperative stop token resolves the in-flight monitor future within the 2.0s R4 drain bound with no cancel/create mutation, and that `MainWindow._drain_monitor_future` then tears down the old provider immediately.
- No change was required to `src/ocobot/ui/main_window.py`: the captured-future + cooperative-stop + bounded-drain path was already correct; R5 verified it and now regression-guards it.
- Full offline suite now **70 passed** (baseline 66 + 4 new), 0 failures, 0 errors.

## R4 — CLOSED WITH VERIFICATION
R4 is closed because implementation, targeted regression coverage, and the offline suite all passed at the checkpoint above.

One targeted design consideration remains for future UI-focused review only: the deferred `on_drained` callback may execute from the future's worker thread; verify whether provider teardown must be marshalled to the Qt/UI thread before making any unrelated change.

## R5 — CLOSED WITH VERIFICATION
R5 is closed: parameterised regression coverage was added and the offline suite is green.

- Implementation: `tests/test_stop_token.py` (new).
  - `test_stop_token_resolves_monitor_future_within_2s[none|get_oco]`: submits the monitor future on a single-worker `ThreadPoolExecutor` (mirrors `MainWindow._monitor_workers`), signals the coordinator's cooperative stop token, and asserts the future resolves within the 2.0s R4 drain bound with `result is None or result.state == ABORTED_NO_CREATE`, `provider.cancelled == []`, `provider.placed == []`, `coordinator._failed is False`.
  - `test_drain_closes_old_provider_after_stop_token[none|get_oco]`: after the stop token resolves the future, `MainWindow._drain_monitor_future(future, close, timeout=2.0)` runs old-provider teardown immediately (no deferral) with no cancel/create overlap.
- `main_window.py` behaviour verified — no code change required. `_switch_mode` captures the in-flight future before `_stop_dynamic_monitor` clears it, signals the cooperative stop, and drains via `_drain_monitor_future`. NEXT.json had listed `main_window.py` in files_to_touch as a possible tweak; none was needed.
- Verification actually run at this checkpoint:
  - Targeted: `pytest tests/test_stop_token.py -p no:cacheprovider -v` -> **4 passed** (~3.2s).
  - Full offline suite: `pytest --ignore=tests/test_testnet_acceptance.py -p no:cacheprovider` -> **70 passed** (~44s), 0 failures / 0 errors.
- No unresolved R5 correctness/safety/lifecycle defect. The previously noted "deferred `on_drained` callback may run on the future's worker thread" item remains a future UI-review consideration only (R4-closed), not an R5 blocker. LIVE remains gated.
- The new test is in the working tree (uncommitted); this checkpoint does not commit it.

## Engineering Plan
The high-level plan was established by the previous Architect (Sonnet) and is the baseline for Opus execution. Do not replace or reorder it during ordinary execution.

### R5 — DONE (Cooperative stop regression) — current pointer: Gate 1 (BLOCKED: awaiting Binance Testnet credentials)
- Use the existing R5 scope from `NEXT.json`.
- Add/complete the targeted stop-token regression coverage and verify the relevant `main_window.py` behavior.
- Acceptance: regression coverage passes and the offline suite remains green.

### Gate 1 — Testnet acceptance
Run `tests/test_testnet_acceptance.py` with real Binance Testnet credentials. Do not modify the acceptance test just to make it pass.

### Gate 2 — Human safety review
Human review of the LIVE order-submission path. LIVE stays disabled until explicitly approved.

### Final — LIVE enablement
Only after Gate 1 and Gate 2: review/retain explicit user confirmation for LIVE, then consider enabling LIVE.

### Final regression
Run the strongest appropriate final suite, including Testnet acceptance when credentials/environment are available.

## Architect vs Executor
**Architect (Sonnet):** broad repository analysis, architecture, risks, milestones, persistent plan.

**Executor (Opus):** execute the existing plan. Do not rebuild the project analysis from scratch when current state and plan exist. Opus may make a targeted deviation only when a concrete correctness, safety, lifecycle, or testability problem prevents the current stage from closing; record the reason and evidence and keep the same stage active until resolved.

## Fast Context Recovery
At session start:
1. Read `NEXT.json`.
2. Read only the relevant current sections of this file.
3. Check `git status` and current `HEAD`.
4. Inspect only files directly required by the current task.
5. Start implementation as soon as sufficient context exists.

Do not perform broad repository rescans or recreate the Architect's work unless a concrete implementation question requires targeted reading.

## Fixed Plan, No Unnecessary Replanning
Use the Architect's plan as the baseline. Do not rewrite, reorder, or substantially expand it during ordinary Opus execution. Safety/correctness defects may be fixed within the current stage; do not carry a known blocking defect forward just because `NEXT.json` points to the next stage.

## Stage Exit Gate — NO SKIPPING
A stage is CLOSED only when:
1. intended implementation is present;
2. relevant verification was actually run;
3. acceptance criteria are satisfied;
4. no known unresolved correctness/safety/lifecycle defect remains for that stage;
5. this file records the evidence.

"Implemented" != "verified". "Tested" != automatically "safe". `NEXT.json` does not override an unresolved defect.

## No Unnecessary Rereading / Test Discipline
Before advancing, perform only a targeted closure review of changed code, relevant tests, and acceptance criteria. Do not re-audit the entire repository between stages. Use focused tests while iterating when needed; run the required suite at the checkpoint once. Never report a test result that was not actually run, and do not repeat an expensive suite without a concrete reason such as a code change after failure.

## Continuous Checkpointing
This is a live engineering handoff. Update it at meaningful milestones, after important decisions, after discovering blockers, at stable verification checkpoints, and before potentially interruptible long operations. Preserve the actual repository state, verified results, risks, decisions, and exact next continuation point.

## Safety / Scope
Keep the project focused on Binance Spot OCO order management/editing. Preserve exact order isolation by `orderListId`. Do not introduce unrelated market-order trading functionality. Treat cancel/create replacement, async lifecycle, provider teardown, stale results, order identity, and LIVE/Testnet boundaries as safety-critical. Never silently enable LIVE.

## Git Hygiene
Do not reset/discard unrelated work. Do not commit credentials, scratch/debug artifacts, or generated files. Inspect diffs before committing. Keep checkpoints coherent. The actual Git repository state takes precedence over stale prose in this file.
