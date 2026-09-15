# OCObot — Agent State (Persistent Continuity)

_Last updated: 2026-09-15 — Postman Agent session (authored the guarded Testnet acceptance test)._

Maintenance rule: update this file when a MAJOR fact changes (subsystem completed, architecture decision, important test pass/fail, new blocker, stopping point moves). Keep it concise. Do not rewrite fully after minor actions.

## 0. How to use this file (read first, do not full-rescan)
1. Read this file.
2. `git status` and `git log --oneline -10`.
3. Inspect only the files relevant to the current stopping point / your task.
4. Verify only what is necessary; continue from the actual state.
- The LOCAL working tree is the source of truth. Never clone/reset/pull older origin over local work, and never discard uncommitted changes.

## A. Current state
- Project: OCObot — Binance Spot OCO management. Scope = safe monitoring, editing and replacement of ONE selected OCO, identified by `orderListId` (never symbol alone).
- Operating progression: PAPER/DEMO -> TESTNET -> LIVE. LIVE is intentionally DISABLED (BinanceOCOProvider raises if constructed with mode=LIVE).
- Layers: `domain` (models, validation) | `application` (monitor_coordinator, dynamic_monitor, monitor_engine, live_price, dynamic_stop, services; legacy `auto_trail.py` still on disk but UNREFERENCED by the main UI) | `providers` (binance, paper, demo_monitor, sample_data, base) | `ui` (main_window with async Dynamic Monitor + DynamicMonitorPanel; plus dashboard/testnet/stage12 modules).
- Active UI path: canonical asynchronous Dynamic Monitor (has replaced the legacy AutoTrail path).
- Safety constraints in force: exact `orderListId` identity; all operations isolated to the selected OCO; explicit replacement failure states; NO blind retry; never search/modify another OCO as a recovery shortcut; LIVE disabled until safety evidence + human review.

## B. Verified facts
- [VERIFIED 2026-09-15] Test suite: `python -m pytest -q` -> **53 passed, 1 skipped, 0 failed, 0 errored, exit 0** (~6s). The single skip is the new opt-in Testnet acceptance test (skips unless dedicated creds + opt-in flag are set); the other 53 need no credentials or network. Run independently this session.
- [REPORTED — Testnet evidence, historical, NOT re-verified this session] Selective OCO replacement on Testnet: target TUTUSDT old `orderListId` 98130 -> new 98135; control NOTUSDT 97902 left unchanged; measured replacement ~2852.79 ms. Testnet only; NOT a production latency guarantee.
- [REPORTED] Binance payload fix: unsupported `aboveTimeInForce` for `LIMIT_MAKER` identified and fixed (confirmed by unit test test_binance_testnet_setup.py).

## C. Recent work (present in working tree, UNCOMMITTED)
- `src/ocobot/ui/main_window.py`: async Dynamic Monitor wired in — `_start_dynamic_monitor`, `_finish_monitor_start`, `_queue_monitor_price`, `_finish_monitor_price`, `_apply_monitor_result`, `_stop_dynamic_monitor`; generation guards; price coalescing; single-worker ThreadPoolExecutor; rollover to new `orderListId`; monitor shutdown in `closeEvent`. Legacy AutoTrail UI removed.
- `src/ocobot/application/monitor_coordinator.py`: result states `SUCCESS` / `ABORTED_NO_CREATE` / `FAILED_NEEDS_ATTENTION`; explicit pre-cancel vs post-cancel failure distinction; sequence cancel -> get price -> calc levels -> build payload -> place_oco -> verify new `orderListId`, with cancelled-exception tagging.
- `tests/test_monitor_coordinator.py`: FakeProvider unit tests for FAILED_NEEDS_ATTENTION (no retry), ABORTED_NO_CREATE (pre-cancel), and successful rollover (cancelled==[100,200]).
- Docs: README.md, docs/PROJECT_ROADMAP.md, docs/TESTNET.md updated; docs/RELEASE_CHECKLIST.md present.
- NEW (this session) — `tests/test_testnet_acceptance.py`: opt-in, never-LIVE automated Testnet acceptance test for release Gate 1. Exercises the real `DynamicMonitorCoordinator` path end-to-end on Testnet: ensures a target + a control disposable OCO, forces a reposition, and asserts only the selected OCO is replaced (new orderListId) while the control OCO remains open and the old id is gone; cancels the disposable orders it opened in cleanup. Guarded by `pytest.mark.skipif` requiring `BINANCE_TESTNET_API_KEY` + `BINANCE_TESTNET_API_SECRET` + `OCOBOT_RUN_TESTNET_ACCEPTANCE=1`, so it SKIPS in normal runs (no network, no orders). Verified this session that it collects without import errors and skips.

## D. Current stopping point
- Git: branch `main`, HEAD `2f42cab`, `main == origin/main`. Working tree is NOT clean — the Dynamic Monitor feature (section C) is UNCOMMITTED/UNSTAGED, plus a NEW untracked file `tests/test_testnet_acceptance.py`. Nothing is staged.
- Finished: Dynamic Monitor implementation + unit tests + doc updates; legacy AutoTrail removed from UI; guarded Testnet acceptance test authored; suite = 53 passed + 1 skipped (verified today).
- Remaining / release gates:
  - Gate 1 (Testnet acceptance): test is now AUTHORED but NOT yet executed against real Testnet credentials. To run it, see section F.
  - Gate 2 [BLOCKED — needs human]: safety/code review.
  - LIVE stays disabled until both gates complete and release is explicitly approved.
- Housekeeping observations (NOT auto-actions): stray empty files at repo root (`None`, `assert`, `git`, `python`) deleted in working tree but not committed; `src/ocobot/ui/` has no `__init__.py` (may be intentional). `pytest_full.txt` / `pytest_stdout.txt` / `pytest-result.log` at root are test-output logs.

## E. Development direction
- Roadmap phases 0-12 largely implemented (freeze spec, price engine, OCO reader, base/stage-2 UI, home, orders/manual edit, dynamic monitoring calc, monitor engine, safe replacement, monitoring UI, engine tests, paper/demo, testnet). Phase 13 (safety/timing review) pending; Phase 14 (LIVE) not started, gated.
- Dynamic Monitor config inputs: Reposition Trigger Rise %, TP Distance Above Current %, SL Distance Below Current %. Calculations: `TP = live*(1+TP%/100)`; `SL Trigger = live*(1-SL%/100)`; `SL Limit = normalized SL Trigger + 1*tickSize`. Invariant: `SL Trigger < SL Limit < live`. Validation rejects non-finite, non-positive trigger/TP/SL, and SL >= 100.

## F. Next-session context
- Start here (see section 0). Do NOT re-scan the whole repo.
- Most relevant modules: `src/ocobot/application/monitor_coordinator.py`, `src/ocobot/ui/main_window.py`, `src/ocobot/ui/dynamic_monitor_panel.py`, `src/ocobot/application/dynamic_monitor.py`, `tests/test_monitor_coordinator.py`, `tests/test_testnet_acceptance.py`.
- To execute the Testnet acceptance gate (Gate 1): set `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`, and `OCOBOT_RUN_TESTNET_ACCEPTANCE=1` (optional overrides: `OCOBOT_TESTNET_TARGET`, `OCOBOT_TESTNET_CONTROL`, `OCOBOT_TESTNET_QUOTE`), then run `python -m pytest -q tests/test_testnet_acceptance.py`. It places small disposable Testnet orders and cancels them afterwards. Never LIVE.
- Uncommitted work is valuable — preserve it. Human operator can commit/push later via terminal.
- Do NOT enable LIVE. Do NOT modify other OCOs as a recovery shortcut. Keep the project OCO-focused.
- Candidate next work: (1) run Gate 1 with dedicated Testnet creds and record the result here; (2) human safety/code review (Gate 2); (3) resolve housekeeping items only if confirmed unintended; (4) commit the Dynamic Monitor feature after review.
