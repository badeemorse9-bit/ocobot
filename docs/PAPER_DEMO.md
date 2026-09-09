# Interactive Paper Demo

The application includes an interactive Paper Simulator in the same desktop window.

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

## MAX STOP behavior

**MAX STOP is optional.** A manually entered Stop price remains a normal fixed draft value.

When the user presses **MAX STOP**, it arms a dynamic mode for the selected OCO. The displayed Stop value is calculated immediately from the current price, but that value is not treated as final.

At activation, the application refreshes the Stop candidate from the latest available price again before cancellation, and then refreshes it once more immediately after cancellation and before creating the replacement. This means price movements during the activation sequence are reflected as late as the provider can observe them.

Editing the Stop price manually disarms dynamic MAX STOP mode. Editing TP does not disarm it. Selecting another OCO or resetting the demo also clears it.

## Demo sequence

1. Start the application with `python -m ocobot`.
2. Select `OCO 1001` (TUTUSDT) from the table.
3. Change TP/SL fields in the local editor. No exchange action happens.
4. Press **MAX STOP** to arm dynamic mode, or leave it off and use a manual Stop value.
5. Use **MOVE PRICE** to simulate market movement.
6. Press **ACTIVATE**. With MAX STOP armed, the replacement Stop is recalculated as late as possible in the activation path.
7. Use **SIMULATE TP HIT** or **SIMULATE SL HIT** to force the selected original to complete and verify activation must abort.
8. Press **RESET DEMO** and repeat with the failure toggles.

## Important boundary

Paper mode is deterministic and in-memory. It does not connect to Binance and cannot prove exchange/network latency. It validates the application's state model, selection isolation, draft behavior, and recovery paths before Testnet integration.
