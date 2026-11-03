"""Spatial duplicate detection between two routes.

Both routes are sampled at the same spatial interval along their own distance
basis. Routes A and B are duplicates if either has at least
DUPLICATE_MIN_SHARED_FRACTION of its samples within DUPLICATE_MAX_DISTANCE_MILES
of the other route's samples. Route IDs, names, distance, and duration are never
used. Sampling at 0.25 mile keeps the sample-to-sample approximation within
0.125 mile of the true route-to-route distance.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from .geometry import LatLng, haversine_miles, point_at_mile
from .limits import (
    DUPLICATE_MAX_DISTANCE_MILES,
    DUPLICATE_MIN_SHARED_FRACTION,
    DUPLICATE_SAMPLE_INTERVAL_MILES,
)

# Conservative bounds for the length of one degree, so grid cells are never
# smaller than the match distance.
_MIN_MILES_PER_DEGREE_LAT = 68.7
_MILES_PER_DEGREE_LNG_AT_EQUATOR = 69.17


def sample_points(
    geometry: Sequence[LatLng],
    cumulative: Sequence[float],
    interval_miles: float = DUPLICATE_SAMPLE_INTERVAL_MILES,
) -> list[LatLng]:
    total = cumulative[-1]
    count = int(total // interval_miles)
    miles = [index * interval_miles for index in range(count + 1)]
    if total - miles[-1] > 1e-9:
        miles.append(total)
    return [point_at_mile(geometry, cumulative, mile) for mile in miles]


class _SampleIndex:
    """Grid hash of sample points for fixed-radius neighbour lookups."""

    def __init__(self, points: Sequence[LatLng], radius_miles: float, max_abs_lat: float):
        self._radius = radius_miles
        self._cell_lat = radius_miles / _MIN_MILES_PER_DEGREE_LAT
        cos_lat = max(math.cos(math.radians(min(max_abs_lat, 89.0))), 1e-6)
        self._cell_lng = radius_miles / (_MILES_PER_DEGREE_LNG_AT_EQUATOR * cos_lat)
        self._cells: dict[tuple[int, int], list[LatLng]] = defaultdict(list)
        for point in points:
            self._cells[self._cell(point)].append(point)

    def _cell(self, point: LatLng) -> tuple[int, int]:
        return (math.floor(point[0] / self._cell_lat), math.floor(point[1] / self._cell_lng))

    def has_neighbour(self, point: LatLng) -> bool:
        row, col = self._cell(point)
        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                for other in self._cells.get((row + d_row, col + d_col), ()):
                    if haversine_miles(point, other) <= self._radius:
                        return True
        return False


def shared_fraction(samples: Sequence[LatLng], other_samples: Sequence[LatLng]) -> float:
    """Fraction of ``samples`` within the match distance of ``other_samples``."""
    if not samples or not other_samples:
        return 0.0
    max_abs_lat = max(abs(lat) for lat, _ in (*samples, *other_samples))
    index = _SampleIndex(other_samples, DUPLICATE_MAX_DISTANCE_MILES, max_abs_lat)
    shared = sum(1 for point in samples if index.has_neighbour(point))
    return shared / len(samples)


def are_duplicates(samples_a: Sequence[LatLng], samples_b: Sequence[LatLng]) -> bool:
    return (
        shared_fraction(samples_a, samples_b) >= DUPLICATE_MIN_SHARED_FRACTION
        or shared_fraction(samples_b, samples_a) >= DUPLICATE_MIN_SHARED_FRACTION
    )
