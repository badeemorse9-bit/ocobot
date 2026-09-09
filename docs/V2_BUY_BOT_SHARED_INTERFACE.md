# V2 — Shared Account, Shared Interface and V1 Interoperability Addendum

> **Status:** Design/specification only. This is part of the V2 Buy Bot contract and does not change V1 execution behavior today.

## 1. One application, one interface

V1 OCO Safe Editor and the future V2 Buy Bot must live inside the **same desktop application and the same main user interface**.

The user must not need to open two separate applications, two separate desktop windows with independent authentication systems, or two separate Binance configurations merely because there are two functional modules.

The UI may present clear tabs/panels/modes such as:

- `OCO Editor (V1)`
- `Buy Bot (V2)`

but both are modules of the same application.

## 2. One Binance account connection / one credential set

The two modules must use the **same configured Binance account connection**.

There must be one shared authentication/configuration layer for the application rather than a separate API key/secret configuration for each bot.

The intended architecture is:

`One Binance account configuration → One shared provider/client layer → V1 and V2 modules`

The credentials are configured once for the application and are not duplicated into V1 and V2 settings stores.

The persistent V2 Buy Bot settings store must never contain API secrets.

The application may expose connection status centrally so the user can see whether the shared Binance connection is ready.

## 3. What V2 creates must be visible to V1

V2 and V1 are logically separate modules, but they operate on the **same Binance account and the same live account orders**.

Therefore, when V2 completes a buy operation and creates an active Binance **OCO protection order**, that OCO belongs to the shared Binance account and must subsequently be discoverable by V1's normal open-OCO listing/refresh flow.

Example:

1. V2 buys Coin A.
2. V2 creates the intended sell/Stop protection OCO for Coin A.
3. The OCO remains open on Binance.
4. User switches to `OCO Editor (V1)`.
5. V1 refreshes the account's open OCO lists.
6. The OCO created by V2 appears in the same list of currently open OCOs.
7. User may select that exact OCO and use V1's existing safe edit/replace workflow.

This is the required interoperability behavior.

## 4. V1 must treat a V2-created OCO as an ordinary open OCO

V1 must not need to know that an OCO was originally created by V2.

If Binance reports it as an active/open OCO and the returned data satisfies V1's supported OCO model, V1 should treat it exactly like any other eligible OCO:

- show it in the open-OCO list;
- allow the user to select it;
- load its actual Binance-returned fields;
- allow the user to prepare a replacement;
- on activation, operate only on that selected OCO identity.

V1 must continue to use the actual Binance `orderListId` and child-order identity returned by the exchange. It must not rely on an internal V2 identifier.

## 5. Important boundary: V1 edits the OCO, not the historical Buy Bot operation

When V1 selects a V2-created OCO, V1 is editing the **current live OCO on Binance**.

V1 does not need to preserve or modify V2's historical settings such as:

- original Buy Amount;
- original Sell Target percentage;
- original Dynamic MAX STOP setting;
- original buy workflow state.

Those are V2 history/settings, not the current V1 OCO identity.

The live OCO values returned by Binance are the authoritative values shown to V1 for editing.

## 6. V2 must not secretly edit through V1

Although both modules share the same account and interface, V2 must not silently invoke V1's OCO replacement logic after a buy unless that behavior is explicitly part of the V2 workflow and separately approved.

Normal V2 flow is:

`Buy → determine actual fill → calculate sell price → calculate/provide Stop → create protection order`

Normal V1 flow is:

`Select existing OCO → prepare replacement locally → activate selected OCO replacement`

The modules share infrastructure and exchange visibility, but their execution responsibilities remain separate.

## 7. Shared provider/client architecture

The implementation should use one shared Binance provider/client configuration for the application.

V1 and V2 may have separate service classes and separate state machines, but they should depend on the same exchange integration boundary rather than maintaining separate credential/session stacks.

Conceptually:

`UI Shell`

`├── OCO Editor Service (V1)`

`├── Buy Bot Service (V2)`

`└── Shared Binance Provider / Account Connection`

This avoids configuration drift and makes it possible for both modules to observe the same account state.

## 8. Order visibility rule

The fact that both modules share one account does **not** mean every order type must appear in every module.

V1 is an OCO editor and its primary order list is the set of open OCOs supported by V1.

Therefore:

- A V2-created **active OCO protection order** must be visible/selectable in V1.
- A standalone buy order is not required to appear in V1's OCO list merely because it originated in V2.
- V1 should not invent a representation for an order type that V1 does not support.

The important interoperability requirement is the resulting active OCO protection: **once it exists on the shared Binance account, V1 can discover and edit that OCO.**

## 9. Refresh behavior

When the user switches from V2 to V1, V1 should refresh/re-read the current open OCOs rather than relying only on an old in-memory list from before the V2 operation.

This ensures an OCO created moments earlier by V2 can appear without requiring an application restart.

The same principle applies in reverse: V2 should read fresh exchange state when beginning a new operation rather than assuming V1's previous local state is still current.

## 10. Shared connection does not mean shared persistent settings

The following are application-level/shared:

- Binance account connection;
- API client/provider;
- connection status;
- exchange metadata access.

The following remain module-specific:

- V1 selected OCO state;
- V1 replacement draft;
- V2 persistent Buy Amount;
- V2 persistent Sell Target;
- V2 persistent Dynamic MAX STOP setting;
- V2 current buy/fill state.

In particular, changing a V1 OCO must not change the saved V2 template, and changing V2's `100 USDT / 2% / Dynamic ON` settings must not change V1's selected OCO.

## 11. Single interface example

The final application should feel like one tool, not two unrelated programs.

Example layout concept:

`OCObot`

`[ OCO Editor ] [ Buy Bot ]`

Shared top-level area:

`Binance Account: Connected`

`Mode: PAPER / TESTNET / LIVE`

Then the selected module shows its own controls.

V1 shows open OCOs and its safe editor.

V2 shows its persistent Buy Amount / Sell Target / Dynamic MAX STOP settings and its buy workflow.

The user authenticates/configures the account once for the application.

## 12. Final V2 → V1 lifecycle requirement

The complete intended cross-module lifecycle is:

`V2 Buy Bot`

→ user selects/configures a coin

→ persistent settings load automatically (for example `100 USDT`, `2%`, Dynamic MAX STOP ON)

→ user activates the buy workflow

→ actual buy fill is obtained

→ `2%` is converted to a real Binance sell price from the actual execution price

→ Dynamic MAX STOP is finalized from the latest valid market/exchange data when enabled

→ protection OCO is created on the shared Binance account

→ user opens `V1 OCO Editor`

→ V1 refreshes open OCOs

→ the V2-created OCO appears

→ user selects that exact OCO

→ V1 can safely prepare/edit/replace it using its normal workflow

No separate Binance account, API-key pair, or second application is required.

## 13. Safety and testing requirements

Paper tests must prove that V2-created simulated OCOs become discoverable by the simulated V1 OCO list.

Testnet must prove that an OCO created by V2 can be read by the same shared Testnet account connection used by V1 and then selected by V1.

Tests must also prove that:

- V1 and V2 do not overwrite each other's persistent settings;
- switching modules does not lose the shared connection;
- refreshing V1 after V2 creation discovers the new OCO;
- V1 acts only on the exact selected `orderListId`;
- V2 does not accidentally reuse V1's selected order identity.

## 14. Implementation gate

This addendum becomes part of the V2 design contract.

V2 remains **post-V1**. First complete and validate V1 OCO Safe Editor. Then implement V2 inside the same application using the shared connection and interoperability rules defined here.
