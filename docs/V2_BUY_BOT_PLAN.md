# V2 — Separate Dynamic Buy Bot Specification

> **Status:** Design/specification only. This module is **not implemented in V1**.
>
> **Priority:** Implement only after the current V1 OCO Safe Editor is completed, tested, validated and accepted.

## 1. Purpose

V2 adds a **separate Buy Bot module inside the same desktop application**.

It must remain logically and operationally isolated from the current V1 OCO Safe Editor. The V1 module continues to edit/replace one already-active Binance Spot OCO. V2 is a separate buy workflow with its own settings, state, validation and execution lifecycle.

The core user experience is:

**prepare the buy/protection parameters first → keep the user's last settings automatically → use the latest market/exchange data at activation → calculate Binance-required prices from the user's percentage settings → submit the actual numeric prices and quantities required by Binance.**

---

## 2. Important distinction: user settings vs Binance order fields

The user should be able to work with convenient **percentage-based settings**, while Binance requires concrete numeric order values.

Therefore:

- The user-facing **Sell Target** is a percentage, for example `2%`.
- Binance must receive an actual sell price, not the text `2%`.
- The bot must calculate that sell price from the **actual executed buy price/fill data**, then convert/round it according to the current symbol filters before submission.
- The UI may display both the user setting and the currently calculated Binance price, but the percentage setting itself remains the persistent user preference.

Example:

`Actual buy price = 0.06000 USDT`

`Sell Target = 2%`

`Calculated sell price = 0.06000 × 1.02 = 0.06120 USDT`

Binance receives `0.06120` (subject to exchange tick/price rules), not `2%`.

The same principle applies to quantity: the user's setting is **USD value**, while Binance may require the final **asset quantity** according to the actual execution and symbol lot/step rules.

---

## 3. Persistent settings outside the order

V2 must have a dedicated **settings area outside the currently selected order/work item**.

At minimum it contains:

- **Buy Amount (USD)**
- **Sell Target (%)**
- **Dynamic MAX STOP** ON/OFF

These are **sticky last-used settings**.

### 3.1 Sticky behavior

If the user changes the settings to:

- Buy Amount = `100 USDT`
- Sell Target = `2%`
- Dynamic MAX STOP = `ON`

then those exact settings remain the current defaults after the operation finishes.

When the user next opens/selects:

- another order for the same symbol,
- another order for a different symbol,
- or starts another buy operation,

the V2 settings must still show:

`100 USDT / 2% / Dynamic MAX STOP ON`

unless the user explicitly changed them.

The system must **not reset them merely because the selected symbol/order changed**.

### 3.2 Manual edits are the only normal source of change

The settings change because the user changes them (or intentionally resets them).

Market-price movement, symbol changes, opening/closing an order context, or completing an operation must not silently overwrite the saved Buy Amount or Sell Target.

### 3.3 Persistence across application restarts

The last saved V2 settings should be restored when the application is reopened.

Persistence must be separated from live order state. It must not remember an old symbol/order ID as the next target.

The persistent settings store must never contain API credentials/secrets.

---

## 4. How a new buy operation uses the saved settings

The saved settings are the **starting values for every new buy operation**.

Example:

1. User previously saved `100 USDT` and `2%`.
2. User opens another coin.
3. The Buy Bot automatically loads `100 USDT` and `2%`.
4. User does not need to type them again.
5. User can still edit them before activation.
6. Any edited values become the new saved values.
7. The operation uses the values applicable at activation.
8. After completion, the same latest settings remain ready for the next coin.

This means the settings behave as a **persistent working template**, while the selected symbol/order remains a separate per-operation identity.

---

## 5. Dynamic MAX STOP

Dynamic MAX STOP is optional and user-controlled.

It must never become active silently just because the feature exists.

### 5.1 OFF / manual mode

When Dynamic MAX STOP is OFF:

- the user controls the Stop value manually;
- price movements must not rewrite the manual Stop value;
- switching coins/orders must not turn Dynamic MAX STOP ON;
- the manually configured value remains stable until the user changes it.

### 5.2 ON / dynamic mode

When Dynamic MAX STOP is ON:

- the UI may show a live candidate based on the latest observable price and current exchange symbol rules;
- the displayed candidate is only a **current preview**, not a permanent final value;
- the candidate must be recalculated as market conditions change;
- the final submitted Stop must be recalculated as late as practically possible before the protection order is actually created/activated;
- current symbol filters/tick size and the provider's latest market observation must be used for the final calculation;
- the final number sent to Binance must obey Binance's current exchange rules.

### 5.3 Last-moment recalculation rule

The bot must not rely on a value calculated several seconds earlier when the user finally activates the operation.

At activation, the sequence must conceptually be:

1. obtain the latest available market data;
2. calculate the dynamic Stop candidate;
3. perform the buy workflow;
4. obtain the latest executed buy/fill information;
5. recalculate the percentage-based sell price from the actual buy price;
6. if Dynamic MAX STOP is enabled, obtain the latest possible price/rule data again as close as possible to protection-order creation;
7. construct the final Binance payload;
8. submit the protection order.

The implementation may combine or reorder network-safe steps where Binance's exact order lifecycle requires it, but it must preserve the central requirement: **the final protection values come from the newest valid data available immediately before submission, not from an old preview.**

### 5.4 Dynamic mode persistence

If the user leaves Dynamic MAX STOP ON, it remains ON for the next operation until the user explicitly turns it OFF.

This differs from V1's per-selected-OCO dynamic behavior: V2 treats the Dynamic MAX STOP switch itself as part of the persistent Buy Bot settings template.

---

## 6. Buy Amount (USD) rules

The user enters a monetary amount, for example:

`100 USDT`

The bot must use that setting to determine the intended spend for the selected asset.

Important rules:

- The user-facing setting is a **quote-currency amount**, not a hard-coded asset quantity.
- Final asset quantity must be derived using the actual executable price/fill information required by the implemented buy order flow.
- Current Binance minimum-notional, quantity-step and related symbol restrictions are authoritative.
- The bot must never assume that `100 USDT` can always be submitted exactly as entered if Binance's current filters require adjustment.
- Any required adjustment/rounding must be explicit and exchange-rule-driven, not an invented safety restriction.
- The bot must clearly distinguish **configured amount** from **actual submitted/executed amount**.

---

## 7. Sell Target (%) rules

The user enters a percentage, for example:

`2%`

The system converts this to a concrete Binance sell price using the **actual buy execution price**, not an arbitrary earlier market preview.

For a positive target percentage:

`Sell Price Before Exchange Rounding = Actual Buy Price × (1 + Sell Target / 100)`

Example:

`Actual Buy Price = 0.06000`

`Sell Target = 2%`

`Sell Price = 0.06120`

Then the result is normalized according to Binance's current price filter/tick-size rules before submission.

### 7.1 No stale-price calculation

The bot must not permanently calculate the sell price when the user first opens the coin and then reuse that number after the actual buy executes at a different price.

The actual fill information is authoritative for the final percentage conversion.

### 7.2 Partial/multiple fills

The implementation must account for the actual execution structure supported by the chosen buy order flow.

If Binance returns multiple fills, the service must use an exchange-correct effective execution price (for example, a quantity-weighted average when appropriate) rather than blindly using the first fill price.

The exact fill handling must follow the actual Binance response fields available from the implemented API operation.

---

## 8. Relationship between Buy, Sell and Stop

The user configures:

- a dollar amount to buy;
- a percentage target for selling;
- optionally, Dynamic MAX STOP.

The system then converts those human-friendly settings into the concrete order parameters required by Binance.

The Buy Bot must never send a percentage where Binance expects a price.

It must also never assume that a Stop setting remains valid simply because it was valid when the user first opened the screen. Final exchange validation happens using current symbol rules and the current order state immediately before submission.

The exact Binance order type/parameter combination used for the buy and protection lifecycle must be based on the actual supported Binance Spot API operation chosen during implementation. The specification intentionally does **not** invent undocumented field names.

---

## 9. Symbol/order selection safety

Persistent settings are reusable values only. They are **not** a persistent order identity.

Every new operation must obtain the current target explicitly.

The system must never automatically carry forward:

- an old symbol,
- an old order ID,
- an old `orderListId`,
- an old quantity,
- an old calculated sell price,
- an old calculated Stop price,

as the target of a new operation merely because those values belonged to the previous operation.

The user's persistent template may carry forward `100 USDT`, `2%`, and Dynamic MAX STOP ON, but not the identity of the previous order.

---

## 10. Separation from V1

V2 must not mutate or reuse V1's selected-OCO execution state.

Separate components/state should exist for:

- V2 persistent settings;
- current V2 operation draft;
- V2 execution state;
- V2 buy/fill data;
- V2 calculated sell price;
- V2 dynamic Stop state.

V1 remains responsible for the existing selected-OCO replacement workflow.

No V2 action may silently cancel, edit or replace an existing V1 OCO unless a future requirement explicitly defines such behavior and it is separately reviewed.

---

## 11. User interface requirements

The V2 UI should expose the persistent settings **outside the individual order form** so that the user can see that they are reusable defaults rather than values belonging to one specific coin.

Recommended structure:

### Persistent Buy Bot settings panel

`Buy Amount (USDT): [ 100 ]`

`Sell Target (%): [ 2.00 ]`

`Dynamic MAX STOP: [ ON ]`

These values remain visible while the user moves between symbols/orders.

### Current operation panel

The selected symbol/order context is shown separately.

The current operation receives the saved settings automatically.

When Dynamic MAX STOP is ON, the UI can additionally show:

- current market price;
- current dynamic Stop candidate;
- time/age of the latest calculation;
- exchange-rule/precision status where useful.

The dynamic candidate is informational until the final activation flow constructs the real order payload.

---

## 12. Reset behavior

The user should have an explicit reset mechanism for V2 persistent settings.

Reset must be deliberate.

A new symbol, a completed order, an application restart, or a rejected order must not automatically reset the saved template.

---

## 13. Validation and exchange authority

Binance's actual response and current symbol rules are authoritative.

The implementation must:

- read actual exchange-returned fields;
- use actual current symbol filters;
- honor price tick size;
- honor quantity step size;
- honor minimum/maximum quantity when applicable;
- honor minimum notional/notional rules when applicable;
- handle exchange rejection explicitly;
- avoid inventing unsupported Binance parameters or field names.

The bot should distinguish between:

1. **user configuration errors**;
2. **exchange-rule validation failures**;
3. **network/provider failures**;
4. **execution/fill-state failures**;
5. **protection-order creation failures**.

No silent fallback should replace a rejected value with an arbitrary alternative.

---

## 14. Execution safety

The Buy Bot is an execution tool, not a strategy engine.

It must not invent entry signals, profit targets, Stop levels, position sizes, or trading decisions outside the user's explicit settings.

The user's configured settings are the source of intent. Exchange data is the source of execution truth.

The final protection order should only be created after the buy execution state is known well enough to derive the actual quantity and actual sell-price target required by Binance.

If a protection order cannot be created correctly, the system must enter an explicit attention/error state rather than pretending the protection exists.

No blind automatic retry should be introduced without a separately specified safety policy.

---

## 15. Timing principle

The user specifically wants the Dynamic MAX STOP to follow price changes **until the moment of activation**.

Therefore the implementation must minimize the gap between:

**latest market observation → final Stop calculation → final protection-order submission**

and should record timing information for debugging/audit purposes.

No implementation should claim a guaranteed execution time unless measured and supported by actual provider/exchange behavior.

---

## 16. Paper → Testnet → Live

V2 follows the same staged safety philosophy as V1:

`PAPER → TESTNET → LIVE`

Paper mode must prove:

- sticky settings persistence;
- symbol switching without settings reset;
- percentage-to-price conversion;
- actual-fill-based sell calculation;
- Dynamic MAX STOP updates;
- last-moment dynamic recalculation;
- quantity/rounding behavior;
- failure states;
- no accidental reuse of previous order identity.

Testnet must validate the real Binance Spot API fields, filters, responses and lifecycle.

Live must remain gated until Paper and Testnet behavior are explicitly validated and reviewed.

---

## 17. Explicit example — the intended user experience

User saves:

`Buy Amount = 100 USDT`

`Sell Target = 2%`

`Dynamic MAX STOP = ON`

User opens Coin A.

The V2 Buy Bot automatically shows:

`100 USDT / 2% / Dynamic MAX STOP ON`

User starts/prepares the operation but waits before activating.

While waiting:

- the `100 USDT` setting remains `100 USDT`;
- the `2%` setting remains `2%`;
- the Dynamic Stop candidate changes with the latest price/rules.

At activation:

- the buy is executed according to the implemented Binance order flow;
- actual fill information is obtained;
- the bot calculates the real sell price from the actual buy price;
- the bot obtains the latest possible market/rule data;
- the Dynamic Stop is recalculated immediately before the protection order is submitted;
- Binance receives concrete numeric price/quantity fields.

After the operation completes, the saved settings remain:

`100 USDT / 2% / Dynamic MAX STOP ON`

The user then opens Coin B.

The same three settings appear automatically, while Coin A's old order identity, old quantity, old sell price and old Stop value are **not** carried into Coin B.

---

## 18. Minimum persistent data model

At minimum, the durable V2 settings record should contain:

- `buy_amount_usd`
- `sell_target_percent`
- `dynamic_max_stop_enabled`

It may later contain additional user preferences that are intentionally defined, but it must not store active order identity as part of the reusable settings template.

Per-operation transient state should separately contain the currently selected symbol/order context and calculated/executed values.

---

## 19. Non-goals for V2

V2 does not automatically become a general trading strategy engine.

Out of scope unless separately approved:

- automatic coin selection;
- technical-analysis signals;
- automatic strategy changes;
- averaging/down-buy logic;
- trailing strategies not explicitly specified;
- background autonomous trading;
- hidden changes to user settings;
- implicit changes to V1 OCOs.

---

## 20. Implementation gate

This document is a design contract for the future V2 Buy Bot.

**Do not implement V2 before V1 is complete and accepted.**

When V2 implementation starts, each rule above should be converted into code-level tests before enabling real execution.
