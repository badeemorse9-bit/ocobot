# AGENT STATE

## Project Goal
Binance Spot OCO safe editor — monitor, edit, and replace ONE selected OCO order by orderListId without freezing the UI.

## Stack
Python 3.11, PySide6, httpx, websockets, pytest

## What's Working Now
- 67 tests green (R1 stop token, R2 rollover rehydration, R3 symbol guard both layers)
- Dynamic Monitor UI with paper provider
- Testnet adapter in place
- Paper provider and rollover state rehydration

## What's Broken Now
- R4 provider-close race: in _switch_mode PAPER branch, old provider is closed before in-flight monitor future drains — can cause freeze or silent exception
- Gate 1 Testnet acceptance tests require real credentials (not run in CI)
- Gate 2 human safety review not done — LIVE mode remains disabled

## Full Plan
1. R4: in _switch_mode PAPER branch add bounded drain of in-flight monitor future before old.close() — file: src/ocobot/ui/main_window.py
2. Verify cooperative stop: confirm monitor thread respects stop token within 2s, no UI freeze on mode switch
3. Gate 1: run test_testnet_acceptance.py with real Binance Testnet credentials and confirm all pass
4. Gate 2: human safety review of LIVE order flow — confirm no accidental live order submission
5. Enable LIVE mode behind confirmation dialog once Gate 1 and Gate 2 pass
6. Final regression: run full pytest suite (including testnet) and confirm 0 failures

## Definition of Success
Project is successful when all tests are green, all tasks in plan are done, and main_window has no freeze with cooperative stop.

## Execution Guide for Claude 4.8
Claude 4.8 you are executor not planner, plan above is ready, your basis of work is to read NEXT.json only and read the file in files_to_touch only, execute ONE task only, you must update NEXT.json yourself with what is done and what is next, then commit, FORBIDDEN to rescan whole project, FORBIDDEN to build a new plan, FORBIDDEN to loop in a closed circle.
