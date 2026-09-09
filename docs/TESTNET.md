# Binance Spot Testnet

The repository now contains a Binance Spot Testnet adapter in `src/ocobot/providers/binance.py`.

## Official Testnet endpoints

Binance documents the Spot Test Network at:

- REST: `https://testnet.binance.vision`
- WebSocket market stream: `wss://stream.testnet.binance.vision/ws`

Spot Testnet supports the `/api/*` endpoints and does not provide the `/sapi/*` environment. The Testnet can reset periodically, so test orders and balances must not be treated as persistent. See the official Testnet documentation before testing.

## Required credentials

Set the following environment variables locally. Never commit them:

```text
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

Install the network dependencies:

```bash
python -m pip install -e .[network]
```

## Current adapter capabilities

- Read open Spot OCO order lists.
- Query one exact OCO by `orderListId`.
- Read each OCO leg's live order details.
- Read live last price.
- Read the symbol `PRICE_FILTER.tickSize`.
- Subscribe to the symbol trade stream for live prices.
- Cancel exactly the selected OCO by `symbol + orderListId`.
- Create a replacement using the current `orderList/oco` endpoint.
- Reject LIVE mode intentionally in this milestone.

The current OCO create endpoint is `POST /api/v3/orderList/oco`; Binance documents the SELL relationship as `above price > last traded price > below stop price`. The cancellation endpoint is `DELETE /api/v3/orderList` and accepts `orderListId` with the required symbol.

## Important activation behavior

The application remains Paper-first. The existing service logic keeps the selected `orderListId` as the immutable target and re-checks the order before cancellation.

When **MAX STOP** is armed, the service reads the latest provider price again before cancellation and once more immediately after cancellation before constructing the replacement request. When MAX STOP is not armed, the manually entered Stop value remains fixed.

There is no atomic cancel-and-create operation in this workflow. A successful cancellation followed by a failed replacement is therefore surfaced as `FAILED_NEEDS_ATTENTION`; the application must not search for or modify any other order.

## Testnet milestone boundary

The adapter is implemented, but the desktop UI is still Paper-only in this milestone. Before exposing a Testnet activation button in the GUI, the next validation step is to run connectivity, authentication, order-list read, exact-order selection, and controlled OCO replacement against a dedicated Spot Testnet account.
