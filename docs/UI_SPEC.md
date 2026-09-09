# UI Specification

## Main layout

### Left: Open OCO Orders

A table containing the currently open OCO lists returned by the provider.

Minimum table columns:

- Order list ID
- Symbol
- Quantity
- Upper/TP price
- Stop price
- List status

The list must represent real provider data; it must not synthesize orders.

### Right top: Live Monitor

Starts only after selection.

- Selected symbol
- Live last price
- Highest currently valid sell-stop candidate
- Original OCO status

This panel is informational and separate from the editor.

### Right bottom: OCO Editor

The editor is a local draft created from the selected OCO.

- Values are pre-filled from the active order.
- TP and Stop Price are editable draft fields.
- Quantity is displayed from the original order and is not recomputed.
- All other exchange-returned fields remain visible through a generic raw-data/advanced section so the app does not pretend to know only a fixed subset of fields.
- No network mutation occurs while editing.
- `ACTIVATE` is disabled when no OCO is selected.

## Visual states

- Green/neutral: original active.
- Drafting: local-only changes.
- Verifying: final exchange check.
- Cancelling/Creating/Confirming: execution progress.
- Success: replacement confirmed.
- Aborted: original changed state before activation.
- Failed Needs Attention: cancellation completed but replacement failed.

Colors are implementation details; the state text must remain understandable without color.
