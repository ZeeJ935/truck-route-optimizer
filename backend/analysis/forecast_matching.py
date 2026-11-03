"""Match a target time to an hourly forecast.

An hour is eligible only within FORECAST_MATCH_WINDOW of the target. The nearest
eligible hour wins, and an exact tie goes to the earlier hour. When no hour is
eligible there is no forecast: weather is never interpolated, repeated, or
borrowed from elsewhere.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .limits import FORECAST_MATCH_WINDOW
from .time_utils import require_aware


def match_forecast_hour(target: datetime, hours: Iterable[datetime]) -> datetime | None:
    require_aware(target, "target")
    best: datetime | None = None
    best_gap = None
    for hour in hours:
        require_aware(hour, "forecast hour")
        gap = abs(hour - target)
        if gap > FORECAST_MATCH_WINDOW:
            continue
        if best is None or gap < best_gap or (gap == best_gap and hour < best):
            best = hour
            best_gap = gap
    return best
