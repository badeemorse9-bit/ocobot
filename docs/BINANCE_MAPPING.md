# Binance API Mapping — V1

This document records the intended exchange boundary. It is based on the current Binance Spot WebSocket API documentation reviewed during implementation.

## Read open OCO lists

Use `openOrderLists.status` to obtain current open order lists. The response includes `orderListId`, `contingencyType`, list status fields, `symbol`, and the member `orderId` / `clientOrderId` pairs. For continuous updates, Binance recommends the authenticated User Data Stream. See the official Account WebSocket API documentation.

## Read one OCO

Use `orderList.status` for the selected `orderListId` when a fresh verification is required. Individual leg details are obtained with the relevant order status endpoint when necessary.

## Cancel selected OCO

Use `orderList.cancel` for the selected symbol/list. V1 must send only the selected order-list identity and must never perform a symbol-wide cancellation.

## Create replacement OCO

Use the current Spot OCO placement endpoint (`orderList.place.oco`) when the Testnet/live adapter is enabled. The payload builder will be driven by the selected order's preserved fields and explicit V1 draft fields. No UI field is invented merely because another interface shows it.

## Live price

After a selection, subscribe to the selected symbol's public market stream. The monitor uses live last-trade price data. The stream layer must reconnect and unsubscribe cleanly when the selection changes.

## Important implementation constraint

Binance's API supports OCO cancellation and placement, but a cancellation followed by a new OCO is not treated as an atomic exchange-side transaction. The app therefore guarantees the *preparation behavior* (no mutation while drafting) but cannot guarantee zero exchange-side latency during the actual replacement.

## Documentation references

- Binance Spot WebSocket API — Account / order lists: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/account
- Binance Spot WebSocket API — Trade / OCO placement and cancellation: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/trade
- Binance Spot WebSocket API — User Data Stream: https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/user-data-stream
