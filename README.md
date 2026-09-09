# OCObot — Binance OCO Safe Editor V1

A focused desktop tool for safely preparing a replacement for a single open Binance Spot OCO order.

## Core principle

The selected OCO remains untouched while the user edits a local draft. Only `Activate` starts the replacement workflow. The application is scoped to the selected `orderListId` and must never act on another order.

## V1 scope

- Binance Spot OCO orders only.
- Read open OCO lists from Binance.
- Select exactly one OCO.
- Load the selected order's live/original data into editable fields.
- Keep the original OCO untouched during drafting.
- Show a separate live-market monitor after selection.
- Show the current last price and a Binance-rule-derived highest currently valid sell stop candidate.
- One activation action for the selected OCO only.
- Paper mode first; Binance Testnet next; live trading only after explicit validation.
- No Market, no standalone Limit, no Trailing Stop, no new-position entry module in V1.

## Safety boundaries

- No withdrawal or transfer permissions are needed by the design.
- No automatic trading decisions.
- No background cancellation while editing.
- No global "replace all" operation.
- Before activation, re-query/verify the selected OCO is still active and still has the same identity.
- If the original OCO has already completed, activation is aborted.
- If cancellation succeeds but creation fails, the app enters a visible `FAILED_NEEDS_ATTENTION` state and does not touch any other order.

## Development stages

1. **PAPER** — no Binance credentials and no network trading calls.
2. **TESTNET** — real API flow against Binance Spot Testnet.
3. **LIVE** — disabled until test evidence and manual review are complete.

## Run locally

```bash
python -m pip install -e .
python -m ocobot
```

Paper UI starts with built-in sample OCOs. No credentials are required.

## Repository map

- `docs/` — specification and safety model.
- `src/ocobot/domain/` — provider-neutral data models and validation.
- `src/ocobot/application/` — selection, draft and activation orchestration.
- `src/ocobot/providers/` — Paper provider and Binance adapter boundary.
- `src/ocobot/ui/` — desktop UI.
- `tests/` — unit and paper-workflow tests.
