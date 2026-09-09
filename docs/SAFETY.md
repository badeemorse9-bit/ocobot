# Safety Invariants

These invariants are part of the product contract and should be tested whenever execution code changes.

1. No exchange mutation during drafting.
2. One active selection at a time.
3. The selected `orderListId` is immutable for an activation attempt.
4. A symbol match is never sufficient to identify the target.
5. Final preflight must verify that the selected OCO still exists and is active.
6. If preflight fails, no cancellation or placement is attempted.
7. If cancellation succeeds but creation fails, enter `FAILED_NEEDS_ATTENTION` and stop.
8. Never automatically cancel, replace, or edit an unrelated order as recovery.
9. Never infer a stop-loss rule from entry price.
10. Never send withdrawals/transfers; V1 has no such capability.
11. Store secrets outside source control. `.env` files are ignored.
12. Live mode remains gated until Paper and Testnet acceptance criteria are met.
