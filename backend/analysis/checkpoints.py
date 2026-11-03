"""Checkpoint placement and the road segment each checkpoint represents.

Checkpoints sit at mile 0, at every multiple of the interval strictly below the
route length, and at the destination. Each checkpoint represents the road
halfway to each neighbouring checkpoint, so segment miles sum to the route length.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .geometry import LatLng, cumulative_miles, point_at_mile
from .limits import ALLOWED_SAMPLING_INTERVALS_MILES

# A multiple of the interval this close to the route length is treated as the
# destination itself, so float noise never creates a near-duplicate destination.
DESTINATION_EPSILON_MILES = 1e-6


@dataclass(frozen=True)
class CheckpointPlacement:
    mile: float
    lat: float
    lng: float
    segment_miles: float


def _validate_interval(interval_miles: float) -> None:
    if interval_miles not in ALLOWED_SAMPLING_INTERVALS_MILES:
        raise ValueError(
            f"sampling interval must be one of {ALLOWED_SAMPLING_INTERVALS_MILES}, got {interval_miles!r}"
        )


def checkpoint_miles(total_miles: float, interval_miles: float) -> list[float]:
    """Mile markers: 0, each interval multiple strictly below the total, then the total."""
    _validate_interval(interval_miles)
    if not math.isfinite(total_miles) or total_miles <= 0:
        raise ValueError(f"route length must be a positive finite number, got {total_miles!r}")

    markers = [0.0]
    multiple = 1
    while True:
        mile = float(multiple * interval_miles)
        if mile >= total_miles - DESTINATION_EPSILON_MILES:
            break
        markers.append(mile)
        multiple += 1
    markers.append(float(total_miles))
    return markers


def segment_miles(markers: Sequence[float]) -> list[float]:
    """Miles represented by each checkpoint, using midpoints between neighbours."""
    if len(markers) < 2:
        raise ValueError("At least an origin and a destination checkpoint are required.")
    for previous, current in zip(markers, markers[1:]):
        if current <= previous:
            raise ValueError("Checkpoint markers must be strictly increasing.")

    midpoints = [(a + b) / 2 for a, b in zip(markers, markers[1:])]
    segments = [midpoints[0] - markers[0]]
    segments.extend(right - left for left, right in zip(midpoints, midpoints[1:]))
    segments.append(markers[-1] - midpoints[-1])
    return segments


def place_checkpoints(polyline: Sequence[LatLng], interval_miles: float) -> list[CheckpointPlacement]:
    """Place checkpoints along the route geometry."""
    cumulative = cumulative_miles(polyline)
    markers = checkpoint_miles(cumulative[-1], interval_miles)
    segments = segment_miles(markers)

    placements = []
    for index, (mile, represented) in enumerate(zip(markers, segments)):
        if index == 0:
            lat, lng = polyline[0]
        elif index == len(markers) - 1:
            lat, lng = polyline[-1]
        else:
            lat, lng = point_at_mile(polyline, cumulative, mile)
        placements.append(CheckpointPlacement(mile=mile, lat=lat, lng=lng, segment_miles=represented))
    return placements
