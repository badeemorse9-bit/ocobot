"""Deprecated compatibility module.

The old Dynamic Stop Distance strategy has been removed. The new monitoring
strategy is documented in docs/AUTO_MONITOR_STRATEGY.md and will be
implemented as a replacement engine after the strategy is finalized.
"""


def dynamic_sell_stop_price(*_args, **_kwargs):
    raise RuntimeError(
        "Obsolete Dynamic Stop strategy removed. Use the new dynamic trade monitoring strategy."
    )


def dynamic_sell_stop_limit(*_args, **_kwargs):
    raise RuntimeError(
        "Obsolete Dynamic Stop strategy removed. Use the new dynamic trade monitoring strategy."
    )
