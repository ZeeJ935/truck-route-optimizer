"""Turn raw route data into a NormalizedRoute on one distance basis.

The provider's route length is the total. Geometry distances (haversine) and
progress distances are scaled so both end at exactly that length, and progress
times are scaled so they end at the provider's travel time.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from analysis.eta import ProgressPoint
from analysis.geometry import LatLng, cumulative_miles
from core.errors import ProviderError

from .types import NormalizedRoute


def _require_positive(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ProviderError(f"Route {name} is missing or invalid.")


def normalize_route(
    points: Sequence[LatLng],
    distance_miles: float,
    duration_seconds: float,
    progress: Sequence[tuple[float, float]],
    source: str,
    travel_modes: Sequence[str] = (),
) -> NormalizedRoute:
    """``progress`` is (miles, seconds) pairs cumulative from the route start."""
    _require_positive("distance", distance_miles)
    _require_positive("duration", duration_seconds)
    if len(points) < 2:
        raise ProviderError("Route geometry is missing.")

    geometry_miles = cumulative_miles(points)
    if geometry_miles[-1] <= 0:
        raise ProviderError("Route geometry has no length.")
    geometry_scale = distance_miles / geometry_miles[-1]
    scaled_geometry = [mile * geometry_scale for mile in geometry_miles]
    scaled_geometry[-1] = distance_miles

    if len(progress) < 2:
        raise ProviderError("Route travel-time progress is missing.")
    first_miles, first_seconds = progress[0]
    if first_miles != 0 or first_seconds != 0:
        raise ProviderError("Route travel-time progress must start at the origin.")
    for (prev_miles, prev_seconds), (miles, seconds) in zip(progress, progress[1:]):
        if not (math.isfinite(miles) and math.isfinite(seconds)):
            raise ProviderError("Route travel-time progress is invalid.")
        if miles < prev_miles or seconds < prev_seconds:
            raise ProviderError("Route travel-time progress is not increasing.")
    last_miles, last_seconds = progress[-1]
    if last_miles <= 0 or last_seconds <= 0:
        raise ProviderError("Route travel-time progress has no length.")

    distance_scale = distance_miles / last_miles
    time_scale = duration_seconds / last_seconds
    scaled_progress = [ProgressPoint(miles * distance_scale, seconds * time_scale) for miles, seconds in progress]
    scaled_progress[-1] = ProgressPoint(distance_miles, duration_seconds)

    return NormalizedRoute(
        geometry=tuple((float(lat), float(lng)) for lat, lng in points),
        cumulative_miles=tuple(scaled_geometry),
        distance_miles=float(distance_miles),
        duration_seconds=float(duration_seconds),
        progress=tuple(scaled_progress),
        source=source,
        travel_modes=tuple(travel_modes),
    )
