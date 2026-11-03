"""Checkpoint ETAs from the routing provider's cumulative travel times.

ETAs assume continuous driving at the provider's travel times, with no rest or
fuel stops. Time is interpolated by distance only between the two provider
progress entries that bracket the checkpoint, which is the most detailed timing
the provider returns.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .time_utils import require_aware

# Tolerance for a checkpoint mile that floats just past the last progress entry.
PROGRESS_END_TOLERANCE_MILES = 1e-6


@dataclass(frozen=True)
class ProgressPoint:
    """Cumulative distance and travel time from the route start."""

    miles: float
    seconds: float


def _validate_progress(progress: Sequence[ProgressPoint]) -> None:
    if len(progress) < 2:
        raise ValueError("At least two progress entries are required.")
    if progress[0].miles != 0 or progress[0].seconds != 0:
        raise ValueError("Progress must start at 0 miles and 0 seconds.")
    for previous, current in zip(progress, progress[1:]):
        if not (math.isfinite(current.miles) and math.isfinite(current.seconds)):
            raise ValueError("Progress entries must be finite.")
        if current.miles < previous.miles or current.seconds < previous.seconds:
            raise ValueError("Progress entries must be non-decreasing in miles and seconds.")


def travel_seconds_at_mile(progress: Sequence[ProgressPoint], mile: float) -> float:
    _validate_progress(progress)
    last = progress[-1]
    if mile < 0 or mile > last.miles + PROGRESS_END_TOLERANCE_MILES:
        raise ValueError(f"mile {mile!r} is outside the route (0 to {last.miles}).")
    if mile >= last.miles:
        return last.seconds

    miles = [point.miles for point in progress]
    index = bisect_left(miles, mile)
    if miles[index] == mile:
        return progress[index].seconds
    start, end = progress[index - 1], progress[index]
    span = end.miles - start.miles
    fraction = 0.0 if span == 0 else (mile - start.miles) / span
    return start.seconds + (end.seconds - start.seconds) * fraction


def eta_at_mile(departure: datetime, progress: Sequence[ProgressPoint], mile: float) -> datetime:
    """UTC arrival time at ``mile``, given a timezone-aware departure."""
    require_aware(departure, "departure")
    seconds = travel_seconds_at_mile(progress, mile)
    return departure.astimezone(UTC) + timedelta(seconds=seconds)
