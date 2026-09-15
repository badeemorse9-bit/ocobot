# Release checklist

## Local completion

- [x] Canonical Dynamic Monitor UI is the default path; legacy AutoTrail UI is unreachable.
- [x] Start and price processing are asynchronous; replacement work is serialized and prices coalesce.
- [x] Start reference/trigger display and successful orderListId rollover are implemented.
- [x] Selection, provider/mode changes, Stop, and close stop monitoring and subscriptions safely.
- [x] ABORTED_NO_CREATE and FAILED_NEEDS_ATTENTION are distinct and visible; no blind retry.
- [x] LIVE remains disabled.
- [x] All Python sources compile and the full local suite passes (53 tests, plus 1 opt-in Testnet acceptance test that skips without credentials).
- [x] Zero-byte artifacts None, assert, git, and python are removed.

## External gates

- [ ] Automated disposable-order Testnet acceptance with dedicated credentials.
      - Test AUTHORED: tests/test_testnet_acceptance.py (opt-in, never LIVE). Validates that
        DynamicMonitorCoordinator repositions only the selected OCO and leaves a separate control
        OCO untouched, then cancels the disposable orders it opened.
      - Runs only when BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET, and
        OCOBOT_RUN_TESTNET_ACCEPTANCE=1 are set; skips otherwise.
      - NOT yet executed against Testnet with real credentials — this box stays unchecked until it is.
- [ ] Human safety/code review.
- [ ] Explicit release approval after both gates.
- [ ] LIVE remains out of scope and disabled.
