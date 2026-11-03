"""Distance helpers for route polylines. Points are (lat, lng) in degrees."""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Sequence

EARTH_RADIUS_MILES = 3958.7613

LatLng = tuple[float, float]


def haversine_miles(a: LatLng, b: LatLng) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def cumulative_miles(polyline: Sequence[LatLng]) -> list[float]:
    """Cumulative distance in miles at each vertex; the first entry is 0."""
    if len(polyline) < 2:
        raise ValueError("A route polyline needs at least two points.")
    totals = [0.0]
    for previous, current in zip(polyline, polyline[1:]):
        totals.append(totals[-1] + haversine_miles(previous, current))
    return totals


def point_at_mile(polyline: Sequence[LatLng], cumulative: Sequence[float], mile: float) -> LatLng:
    """Point on the polyline at ``mile`` from its start, interpolated between vertices."""
    if len(polyline) != len(cumulative):
        raise ValueError("polyline and cumulative distances must have the same length.")
    total = cumulative[-1]
    if mile <= 0:
        return polyline[0]
    if mile >= total:
        return polyline[-1]
    index = bisect_left(cumulative, mile)
    start_mile, end_mile = cumulative[index - 1], cumulative[index]
    start, end = polyline[index - 1], polyline[index]
    span = end_mile - start_mile
    fraction = 0.0 if span == 0 else (mile - start_mile) / span
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )
