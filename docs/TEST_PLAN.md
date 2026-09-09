# Test Plan

## PAPER-01 — Ten orders, one target

Fixture contains multiple OCOs, including multiple lists for the same symbol. Select one list. Assert only that `orderListId` can be cancelled by the activation service.

## PAPER-02 — Drafting does not mutate

Select an OCO, edit TP/SL for any amount of time, and assert the provider has recorded zero cancellations and the original remains ACTIVE.

## PAPER-03 — Fill before activation

Mark the selected original as terminal before pressing Activate. Activation must become `ABORTED`; no replacement payload may be placed.

## PAPER-04 — Selective replacement

Activate OCO #2. Assert #1, #3, and all other lists remain unchanged.

## PAPER-05 — Failure after cancellation

Make the paper provider raise on placement. Assert state is `FAILED_NEEDS_ATTENTION` and no retry touches any other order.

## PAPER-06 — Live monitor follows selection

Select symbol A, verify only A is monitored; switch to symbol B, verify A is unsubscribed and B becomes the active monitor.

## TESTNET acceptance gate

- Read real open OCO lists.
- Select one of several OCOs on the same symbol.
- Verify all returned original fields are preserved in the snapshot.
- Edit one field and confirm the original remains active until activation.
- Exercise activation and inspect resulting order-list IDs.
- Force/reproduce API validation failures and verify safe failure state.
- Capture measured cancellation-to-confirmation latency; record the actual value, do not hard-code a guarantee.

Live mode is not considered accepted until these checks pass and the operator has reviewed the logs and replacement behavior.
