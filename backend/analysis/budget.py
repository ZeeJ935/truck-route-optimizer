"""Weather location budget for one analysis.

Open-Meteo counts each location as one call, and one analysis may request at
most MAX_WEATHER_LOCATIONS_PER_ANALYSIS distinct locations. The budget is applied
in this order:

1. Remove duplicate checkpoint locations across routes first.
2. Reserve at least CORRIDOR_MIN_RESERVED_POINTS corridor locations, so the
   heatmap is never empty.
3. Checkpoints may use the rest of the ceiling.
4. Budget left after checkpoints goes back to the corridor, up to CORRIDOR_MAX_POINTS.
5. If checkpoints still don't fit, reject the request with validation_error and
   suggest a larger sampling interval. Checkpoints are never dropped.

Corridor points that coincide with a checkpoint location cost nothing extra, but
they still count toward the corridor budget, so the total stays within the ceiling.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from core.errors import ValidationFailed

from .corridor import dedupe_locations, thin_evenly
from .geometry import LatLng
from .limits import (
    ALLOWED_SAMPLING_INTERVALS_MILES,
    CORRIDOR_MAX_POINTS,
    MAX_CHECKPOINT_LOCATIONS,
    MAX_WEATHER_LOCATIONS_PER_ANALYSIS,
)


@dataclass(frozen=True)
class WeatherBudget:
    checkpoint_locations: tuple[LatLng, ...]
    corridor_locations: tuple[LatLng, ...]
    corridor_budget: int

    @property
    def all_locations(self) -> tuple[LatLng, ...]:
        """Distinct locations to request: checkpoints first, then new corridor points."""
        return tuple(dict.fromkeys((*self.checkpoint_locations, *self.corridor_locations)))


def _too_many_checkpoints_message(count: int, interval_miles: int) -> str:
    larger = [str(value) for value in ALLOWED_SAMPLING_INTERVALS_MILES if value > interval_miles]
    base = (
        f"This trip needs {count} weather checkpoints, but at most {MAX_CHECKPOINT_LOCATIONS} "
        f"fit within the weather service's limits."
    )
    if not larger:
        return f"{base} The trip is too long to analyze, even at the largest sampling interval."
    return f"{base} Choose a larger sampling interval ({' or '.join(larger)} miles)."


def plan_weather_locations(
    checkpoint_points: Iterable[LatLng],
    corridor_points: Sequence[LatLng],
    interval_miles: int,
) -> WeatherBudget:
    checkpoints = dedupe_locations(checkpoint_points)
    if len(checkpoints) > MAX_CHECKPOINT_LOCATIONS:
        raise ValidationFailed(
            _too_many_checkpoints_message(len(checkpoints), interval_miles),
            fields={"sampling_interval_miles": "Too many checkpoints for this trip at this interval."},
        )

    corridor_budget = min(CORRIDOR_MAX_POINTS, MAX_WEATHER_LOCATIONS_PER_ANALYSIS - len(checkpoints))
    corridor = thin_evenly(dedupe_locations(corridor_points), corridor_budget)
    return WeatherBudget(
        checkpoint_locations=tuple(checkpoints),
        corridor_locations=tuple(corridor),
        corridor_budget=corridor_budget,
    )
