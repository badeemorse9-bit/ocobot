# OCObot V1 — Functional Specification

## 1. Product boundary

V1 is a single-order OCO replacement assistant for Binance Spot. It is not a trading strategy, signal engine, portfolio manager, or general order-entry system.

## 2. Selection rule

The application lists open OCO order lists returned by the exchange. The user explicitly selects one row. From that moment until completion or cancellation, the selected `orderListId` is the only target of the editing and activation workflow.

Ten OCOs on the same symbol remain ten separate targets. Selecting one must never cause a lookup, cancellation, or replacement of another list merely because the symbol is the same.

## 3. Original vs draft

The selected OCO is loaded into an in-memory snapshot/draft. Every field returned by Binance is preserved in `raw` data. The UI may expose fields intentionally, but it must not invent exchange fields or silently manufacture trading rules.

Typing changes only the local draft. There is no exchange request during drafting.

## 4. Live monitor

The live monitor starts only after an OCO is selected. It is visually separate from the editor. It shows the selected symbol's live last price and a continuously refreshed reference value for the highest currently valid sell stop candidate, derived only from exchange constraints known for the symbol/order type.

The monitor is informational. It does not fill the user's draft and does not decide the user's stop or take-profit.

## 5. Editor

The editor is pre-populated from the selected active OCO so the user can modify only what they choose: take-profit, stop, or both. Unchanged fields remain unchanged in the draft. Quantity comes from the selected order and is not recomputed from account balance or entry price.

## 6. Activation

The original OCO remains active until the user presses `ACTIVATE`.

On activation the application:

1. Verifies the selected list still exists.
2. Verifies it is still active/executing.
3. Verifies the identity is still the selected `orderListId`.
4. Validates the prepared draft structurally.
5. Cancels only the selected OCO list.
6. Places the prepared replacement OCO.
7. Confirms the replacement result.
8. Records elapsed execution time and final state.

If the original is no longer active at step 1–3, activation is aborted and no replacement is created.

If cancellation succeeds and replacement creation fails, state becomes `FAILED_NEEDS_ATTENTION`; the application performs no unrelated recovery action on other orders.

## 7. Stop-loss rule

The application must not impose a trading policy such as "stop must be below entry". Exchange validity rules and symbol filters are the authority. The app can show exchange-derived constraints and final API errors.

## 8. Modes

- PAPER: deterministic simulation only.
- TESTNET: real Binance test environment after Paper acceptance.
- LIVE: disabled until explicit acceptance of test evidence.

## 9. V1 non-goals

No Market orders, standalone Limit order manager, Trailing Stop manager, new-position entry, withdrawals, transfers, strategy logic, automatic trailing, or trading recommendations.
