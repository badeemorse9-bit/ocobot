# Paper Simulator

The Paper provider is intentionally more than a static mock. It models the critical safety behavior that the real OCO workflow must preserve.

## Simulated market

`PaperOCOProvider.set_last_price(symbol, price)` updates the current price and immediately evaluates every active OCO for that symbol.

`simulate_market_path(symbol, prices)` applies a deterministic sequence of prices, making scenarios reproducible in tests.

## Simulated OCO behavior

For the paper model:

- Price reaching the upper TP leg fills the TP and cancels its sibling.
- Price reaching the stop trigger fills the SL leg and cancels its sibling.
- Executed/cancelled lists are no longer returned as open OCOs.
- Explicit `force_execute()` can reproduce a race where the selected original order completes before activation.

This is a deliberately simplified fill model. It is not intended to reproduce Binance matching-engine semantics, slippage, partial fills, or network latency.

## Failure injection

The provider exposes deterministic switches:

- `fail_next_cancel = True`
- `fail_next_place = True`

These are used to verify the application's safety state when cancellation fails or when the old OCO has been cancelled but the replacement cannot be created.

## Timing

`activation_timeline` records the paper activation sequence. The intended sequence is:

```text
cancel:<selected-order-list-id>
place:new
```

The service builds and validates the replacement payload before cancellation. This protects the original order from avoidable client-side validation failures.

## Required acceptance scenarios

1. Ten open OCOs, select one, and verify only its list id is cancelled.
2. Edit the draft for an arbitrary amount of time; verify the selected original remains active.
3. Move price into the old TP during drafting; verify the old TP fills and no replacement is created.
4. Move price into the old SL during drafting; verify the old SL fills and its sibling is cancelled.
5. Submit an invalid draft; verify cancellation never occurs.
6. Force replacement creation failure; verify `FAILED_NEEDS_ATTENTION` and all non-selected OCOs remain untouched.
7. Force cancellation failure; verify no replacement is placed.
8. Verify the activation timeline is cancel-then-place only after the Activate action.
