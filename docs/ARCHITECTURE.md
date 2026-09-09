# Architecture

```text
Qt UI
  │
  ▼
Application Services
  │
  ├── Selection Lock
  ├── Draft Manager
  ├── Live Monitor
  └── Activation Orchestrator
          │
          ▼
Domain Models / Validation
          │
          ▼
Provider Interface
      ┌───┴────────┐
      ▼            ▼
   Paper        Binance
   Provider     Adapter
                    │
              REST / WS API
```

## Layer rules

- `ui` never calls Binance directly.
- `application` owns workflow sequencing and selected-order scope.
- `domain` is provider-neutral and contains no network code.
- `providers` translate exchange data into domain objects and expose operations through one narrow contract.
- Paper behavior is deterministic and testable.
- Binance network execution remains gated until Testnet validation is complete.

## Identity model

An OCO is a single `orderListId` containing two order legs with individual `orderId`s. The application keeps both identities in the selected snapshot, but the order-list ID is the hard scope key for activation.

## State machine

`IDLE → DRAFTING → VERIFYING → CANCELLING → CREATING → CONFIRMING → SUCCESS`

Failure states:

- `ABORTED`: preflight says the selected OCO is no longer eligible.
- `FAILED_NEEDS_ATTENTION`: cancellation or creation failed and requires explicit operator attention.

No automatic cross-order recovery exists.
