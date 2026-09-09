# Interactive Paper Demo

The application now includes an interactive Paper Simulator in the same desktop window.

## What the demo proves

- Selecting one OCO locks the workflow to that `orderListId`.
- The selected OCO remains active while the local draft is edited.
- Price can be moved from the UI and active OCO trigger logic is evaluated immediately.
- TP hit completes the selected OCO and cancels its sibling leg.
- SL hit completes the selected OCO and cancels its sibling leg.
- Activation checks the original OCO again before cancelling it.
- A simulated replacement-creation failure produces `FAILED_NEEDS_ATTENTION`.
- A simulated cancellation failure does not create a replacement.
- Other OCOs remain untouched.

## Demo sequence

1. Start the application with `python -m ocobot`.
2. Select `OCO 1001` (TUTUSDT) from the table.
3. Change TP/SL fields in the local editor. No exchange action happens.
4. Use **MOVE PRICE** to simulate market movement.
5. Use **SIMULATE TP HIT** or **SIMULATE SL HIT** to force the selected leg to fill.
6. Notice that the selected original becomes `ALL_DONE` and the editor reports that activation must abort.
7. Press **RESET DEMO**, select an OCO again, prepare a draft, and press **ACTIVATE** to see `cancel → place` in the event log.
8. Enable **Fail next replacement creation**, then press **ACTIVATE** to test the recovery state.

## Important boundary

Paper mode is deterministic and in-memory. It does not connect to Binance and cannot prove exchange/network latency. It validates the application's state model, selection isolation, draft behavior, and recovery paths before Testnet integration.
