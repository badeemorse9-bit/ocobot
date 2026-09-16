# AGENT STATE
> Last updated by: docs-rewrite pass | Baseline: 67 tests green

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
- **67 tests pass** (`pytest --ignore=tests/test_testnet_acceptance.py`) — zero failures, zero errors.
- R1 stop token: monitor thread honours a `threading.Event` stop token; stops within 2 s when signalled.
- R2 rollover rehydration: on symbol switch the state machine re-hydrates open OCO orders from the REST snapshot before subscribing to the stream.
- R3 symbol guard: both UI layer and provider layer reject operations on a symbol that is not the currently loaded one.
- Dynamic Monitor UI renders live order-book and OCO status using the paper provider.
- Testnet adapter wired in; credentials are read from `.env` / environment variables (never hardcoded).
- Paper provider fully functional for offline / CI development.
- Rollover state rehydration confirmed working in unit tests.

---

## What's Broken
- **R4 — provider-close race** (BLOCKER): In `src/ocobot/ui/main_window.py`, inside `_switch_mode`, the PAPER branch calls `old_provider.close()` before the in-flight monitor future has finished draining. This can cause a UI freeze, a silent `asyncio.CancelledError`, or a race-condition log flood when the user switches modes quickly.
- **Gate 1 — testnet acceptance** (BLOCKED on credentials): `tests/test_testnet_acceptance.py` requires real Binance Testnet API key + secret in env. Not run in CI. Must be run manually with valid credentials.
- **Gate 2 — human safety review** (NOT DONE): LIVE mode order submission has not been reviewed by a human for correctness and safety. LIVE mode is currently disabled in the UI. Must stay disabled until Gate 2 is signed off.

---

## Full Plan
All tasks are ordered. Do NOT skip ahead. Do NOT re-order.

### R4 — Fix provider-close race (CURRENT TASK)
- **File:** `src/ocobot/ui/main_window.py`
- **Method:** `_switch_mode` — PAPER branch only.
- **What to do:** Before calling `old_provider.close()`, await/drain the in-flight monitor future with a bounded timeout (≤ 2 s). Use `future.cancel()` then `asyncio.wait_for(shield(future), timeout=2)` or equivalent cooperative drain so the monitor thread can flush its stop sequence cleanly.
- **Acceptance:** Mode switch completes in < 3 s with no exception in logs and no UI freeze. Existing 67 tests still pass.

### R5 — Cooperative stop regression
- **File:** `tests/test_stop_token.py` (add new test) and `src/ocobot/ui/main_window.py` (verify behaviour).
- **What to do:** Add a parameterised pytest test that starts a monitor future, signals the stop token, and asserts the future resolves within 2 s. This is a regression guard for R4.
- **Acceptance:** New test passes. Total test count increases by at least 1.

### Gate 1 — Testnet acceptance
- **Files:** `tests/test_testnet_acceptance.py` (read-only, do not modify).
- **What to do:** Run with real Binance Testnet credentials. All tests must pass.
- **Acceptance:** `pytest tests/test_testnet_acceptance.py` exits 0 with 0 failures.

### Gate 2 — Human safety review
- **What to do:** A human reviewer must read the LIVE order submission code path and sign off that no accidental live order can be placed without explicit user confirmation.
- **Acceptance:** Reviewer adds a signed comment in `docs/SAFETY_REVIEW.md`.

### Final — Enable LIVE mode
- **File:** `src/ocobot/ui/main_window.py`
- **What to do:** Remove the LIVE mode disabled guard. Add a confirmation dialog (QMessageBox) before any live order submission. Confirm Gate 1 and Gate 2 are complete first.
- **Acceptance:** User can place a live order only after explicitly confirming in the dialog. No test regressions.

### Final Regression
- Run full pytest suite **including** testnet acceptance tests.
- **Acceptance:** 0 failures, 0 errors across all test files.

---

## Definition of Success (measurable exit criteria)
The project is DONE when ALL of the following are simultaneously true — no exceptions:

1. `pytest` (full suite, including `tests/test_testnet_acceptance.py`) exits with **0 failures and 0 errors**.
2. UI mode switch (PAPER ↔ TESTNET) completes in **< 3 seconds** with no exception in logs (verified manually).
3. No UI freeze observed during 10 consecutive rapid mode switches (manual smoke test).
4. `docs/SAFETY_REVIEW.md` exists and contains a human sign-off for LIVE order flow.
5. LIVE mode is accessible in the UI **only** behind a QMessageBox confirmation dialog.
6. `NEXT.json` → `next_task` is `"DONE — all gates passed"`.

---

## Execution Guide for Claude 4.8
You are the EXECUTOR. The plan above is final. Follow these steps exactly, one task at a time. No replanning. No full-project rescans.

### Step-by-step rules
1. **Read `NEXT.json` first** — that file tells you the one task to do right now (`next_task`) and the one or two files you are allowed to touch (`files_to_touch`).
2. **Read only the files listed in `files_to_touch`** — do not open any other source files unless they are explicitly listed.
3. **Execute the task described in `next_task`** — implement the change, nothing more.
4. **Run `pytest --ignore=tests/test_testnet_acceptance.py`** — confirm the green count is ≥ the count in `NEXT.json → tests`. If any test regresses, fix it before continuing.
5. **Update `NEXT.json`** — set `last_done` to what you just did, set `next_task` to the next item in the Full Plan above, update `tests` to the current green count, update `files_to_touch` to the files for the next task.
6. **`git add` only the files you touched plus `NEXT.json`** — never stage unrelated files.
7. **`git commit -m "feat: <one-line summary of what you did>"`** — commit message must be lowercase, imperative, ≤ 72 chars.
8. **Stop** — do not proceed to the next task in the same session. The next agent invocation will read `NEXT.json` and continue.

### Hard constraints
- FORBIDDEN: touching `tests/`, `src/ocobot/monitor/`, `src/ocobot/providers/`, `pyproject.toml`, `docs/`, `scripts/`, `README.md` unless they are explicitly listed in `files_to_touch` for the current task.
- FORBIDDEN: rebuilding the plan or rescanning the whole project.
- FORBIDDEN: running pytest more than once per session.
- FORBIDDEN: looping — if pytest fails after your fix, report the failure and stop; do not retry silently.
- FORBIDDEN: `Start-Sleep`, polling temp files, or any background process tricks.
