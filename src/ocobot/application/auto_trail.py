"""Deprecated compatibility module.

The previous Auto Trail rules have been removed. The replacement design is
now Dynamic Trade Monitoring as documented in
`docs/AUTO_MONITOR_STRATEGY.md`.
"""


class AutoTrailSettings:
    def __init__(self, *_args, **_kwargs):
        raise RuntimeError(
            "Obsolete Auto Trail strategy removed. Use the new dynamic trade monitoring strategy."
        )


class AutoTrailEngine:
    def __init__(self, *_args, **_kwargs):
        raise RuntimeError(
            "Obsolete Auto Trail strategy removed. Use the new dynamic trade monitoring strategy."
        )
