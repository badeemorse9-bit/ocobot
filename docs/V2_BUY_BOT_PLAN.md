# V2 — Separate Dynamic Buy Bot Plan

This document defines a future module that will live inside the same desktop interface but remain logically separate from the current OCO Safe Editor.

## Boundary

The current V1 OCO editor is not changed by this module. The future Buy Bot is a separate UI/application layer with its own state, settings, validation, and execution flow.

The V1 OCO editor remains focused on editing/replacing one existing Binance Spot OCO at a time.

## Future Buy Bot concept

The future module will follow the same core safety idea of preparing the operation first and executing only when the user explicitly activates it, but it will be a **buy workflow** rather than an OCO-edit workflow.

The main user-configurable settings are:

- **Buy amount (USD):** the dollar amount to spend on the selected asset.
- **Sell target (%):** the desired percentage above the actual executed buy price at which the sell target should be placed.
- **Dynamic MAX STOP:** an optional mode that uses the highest currently available sell Stop price candidate according to the latest market price and exchange symbol rules.

## Persistent last-used settings

These Buy Bot settings are **sticky settings** and must persist as the user's latest choices:

- If the user enters `100 USD` and `2%`, those values remain `100 USD` and `2%` after the operation completes.
- When the user selects another buy order for the same symbol, the settings remain unchanged.
- When the user selects a different symbol, the settings remain unchanged.
- The settings change only when the user explicitly edits them.
- The last saved values should be restored when the Buy Bot module is reopened/restarted, unless the user intentionally resets them.

This persistence applies to the Buy Bot settings only and must not modify the settings or state of the V1 OCO editor.

## Dynamic MAX STOP behavior

Dynamic MAX STOP is optional. It is not a mandatory validation rule and it must never silently activate.

When the user does **not** enable Dynamic MAX STOP:

- Stop behavior remains based on the user's explicit/manual setting.
- Market-price changes do not rewrite the Stop setting.

When the user **does** enable Dynamic MAX STOP:

- The UI may show the currently calculated Stop candidate while preparing the order.
- The candidate is not treated as final merely because it was calculated earlier.
- Immediately before the final buy workflow creates/activates the protection order, the system must refresh the latest available market price and exchange symbol constraints.
- The Stop value used for the actual submitted protection order must be recalculated as late as the provider can observe it.
- Rapid price movement between user activation and order creation must therefore be reflected in the final dynamic Stop calculation.
- After the buy operation finishes, Dynamic MAX STOP remains enabled for the next operation until the user explicitly disables it.

## Buy and protection relationship

The future module must derive quantity from the user's configured USD amount and the actual buy price/fill information available from the exchange. It must not assume a fixed asset quantity before execution when the final quantity depends on the actual execution result.

The future sell target percentage should be calculated from the actual executed buy price, not from a stale preview price.

The future module must use the exchange's current symbol/order filters and returned fields rather than inventing unsupported Binance parameters.

## Example user flow

1. User opens the separate Buy Bot module.
2. The module shows the last saved settings, for example `100 USD`, `2%`, and Dynamic MAX STOP enabled.
3. User selects an asset/order context.
4. The settings remain `100 USD` and `2%`; the user does not need to re-enter them.
5. User may change any setting manually. The new value becomes the new saved value.
6. User activates the buy workflow.
7. The system uses the latest exchange data available at execution time.
8. The actual executed buy price is used to determine the percentage-based sell target.
9. If Dynamic MAX STOP is enabled, the Stop is recalculated as late as possible before the protection order is created.
10. The completed operation leaves the user's latest Buy Bot settings intact for the next selection.

## Persistence requirements

Settings persistence should be stored separately from order state. The module should have a small durable settings store containing, at minimum:

- `buy_amount_usd`
- `sell_target_percent`
- `dynamic_max_stop_enabled`

The store must be local to the application and must never contain API secrets.

## Safety requirements

- No automatic trading decisions outside the user's configured parameters.
- No automatic change to the current V1 OCO order.
- No automatic carry-over of a specific symbol, order ID, or `orderListId` as the target.
- Persistent settings are values only; order identity is always selected fresh for each operation.
- Dynamic MAX STOP is a user-selected mode, not a default hidden behavior.
- Exchange responses and symbol filters remain authoritative.
- Test sequence remains `PAPER → TESTNET → LIVE`, with Live disabled until explicit validation and review.

## Implementation timing

This module is a **post-V1 feature**. It should not be implemented until the current OCO Safe Editor has been successfully completed, validated, and accepted.
