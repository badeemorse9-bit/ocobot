# OCObot V1 — Functional Specification

## 1. Product boundary

V1 is a Binance Spot OCO management and replacement assistant. It is not a signal engine, portfolio manager, or general order-entry system.

## 2. Selection rule

The application lists active OCO order lists returned by Binance. The user selects one exact `orderListId`. All editing, monitoring, and replacement actions remain tied to that exact order list until a successful replacement creates a new `orderListId`.

Multiple OCOs for the same symbol are independent targets and must never be mixed.

## 3. Original vs draft

Selecting an OCO loads an in-memory snapshot/draft. All exchange-returned fields remain available in the raw payload. Draft changes are local until an explicit activation/replacement operation.

## 4. OCO price model

For a SELL OCO the application must distinguish three prices:

- `TP Sale Price`: the price of the upper LIMIT/LIMIT_MAKER sell leg.
- `SL Trigger Price`: the `stopPrice` that activates the lower stop leg.
- `SL Limit Price`: the limit `price` placed after the stop is triggered.

The UI must never collapse the two stop-leg prices into one field.

## 5. Dynamic Trade Monitoring

Automatic monitoring is optional and is enabled by the user for a selected open OCO.

The monitoring strategy has **three user-controlled percentages only**:

```text
Reposition Trigger Rise %      e.g. 1.00%
TP Distance Above Current %    e.g. 4.00%
SL Distance Below Current %    e.g. 2.00%
```

The user does **not** enter a separate percentage for `SL Limit Price`.

When monitoring starts, the current live price becomes the reference/anchor.

When live price reaches or exceeds:

```text
anchor × (1 + trigger/100)
```

an automatic OCO reposition event is created.

The reposition event is edge-triggered, not a condition that must remain true. Once the trigger is crossed, a small pullback during processing does not invalidate the event.

At reposition time, the new OCO prices are calculated from the newest usable live price selected by the execution flow:

```text
TP Sale Price      = live_price × (1 + TP_distance/100)
SL Trigger Price   = live_price × (1 - SL_distance/100)
SL Limit Price     = SL Trigger Price + 1 × tickSize
```

The system owns the internal relationship between `SL Trigger Price` and `SL Limit Price`. The fixed internal difference is exactly **one exchange tick (`1 × tickSize`)**. It is not a user-controlled percentage.

All prices are normalized to the exchange `tickSize` and checked against current exchange constraints before creation. Normalization must preserve the intended stop relationship; the two stop prices must not collapse to the same tick or reverse their required relationship.

The expected stop relationship for the SELL stop leg is:

```text
SL Limit Price > SL Trigger Price
```

with both remaining below the current market price at creation time, subject to Binance's authoritative rules.

## 6. Gap / jump handling

If price jumps across multiple trigger intervals before the bot can process them, the application must not replay every missed trigger as a chain of cancel/create operations.

Instead:

1. Detect that at least one trigger has been crossed.
2. Coalesce the missed movement into one reposition event.
3. Calculate the new levels from the newest usable live price available to the replacement flow.
4. Perform at most one replacement for that event.
5. Set the replacement's latest usable live price as the next monitoring anchor.

## 7. Processing lock

Only one automatic replacement may be in flight for a monitored OCO at a time. New price updates received while the replacement is busy are recorded as latest price state, not launched as parallel replacements.

## 8. Replacement safety

Before automatic replacement:

1. Re-query the exact selected `orderListId`.
2. Confirm it still exists, is still active/executing, and still matches the selected symbol/identity.
3. Capture the latest usable live price.
4. Build and validate the replacement OCO.
5. Cancel only the selected OCO.
6. Refresh the latest usable price before placement.
7. Revalidate the final replacement relationship.
8. Create the replacement.
9. Confirm the new `orderListId`.
10. Record elapsed time and final state.

If the original order completes before cancellation, stop monitoring and create nothing.

If cancellation succeeds but replacement creation fails, enter `FAILED_NEEDS_ATTENTION`; do not blindly retry or touch unrelated orders.

## 9. Manual replacement

Manual replacement follows the same exact-order identity and safety rules. The user may edit TP, SL Trigger, and SL Limit independently in the draft before activation.

## 10. Modes

- `PAPER`: deterministic simulation only.
- `TESTNET`: real Binance Testnet after Paper acceptance.
- `LIVE`: disabled until explicit acceptance of the full test evidence.

## 11. Non-goals

No Market-order module, standalone Limit manager, new-position entry, withdrawals, transfers, strategy recommendations, or unrelated portfolio automation in V1.
