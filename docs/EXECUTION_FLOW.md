# Activation Flow

The activation button is intentionally the only point at which the original OCO may be changed.

```text
USER SELECTS OCO
      │
      ├── snapshot original data
      ├── lock target = orderListId
      ├── start selected-symbol live monitor
      └── open local draft

DRAFTING
      │
      ├── user edits TP / SL fields
      ├── no Binance mutation
      └── original OCO remains active

ACTIVATE
      │
      ├── re-read selected order list
      ├── verify still active
      ├── verify same orderListId
      ├── validate draft
      │
      ├── cancel selected OCO only
      │
      ├── create replacement OCO
      │
      └── confirm result
```

## Timing

The app should capture monotonic timestamps around each exchange operation so the real cancellation-to-confirmation duration can be measured. The application must not promise a fixed maximum latency; network and exchange conditions control actual time.

## No implicit re-selection

A failure, fill, cancel, or status transition never causes the app to choose another order. The selected identity stays fixed until the workflow ends or the user explicitly selects a different OCO.
