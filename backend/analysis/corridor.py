"""Heatmap corridor points along the final routes.

Each route is sampled every CORRIDOR_SPACING_MILES (including its start and end).
Each sample gives one centre point on the route and one point
CORRIDOR_SIDE_OFFSET_MILES to each side, perpendicular to the local direction of
travel. Points shared between routes are deduplicated by rounded coordinate.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from routing.types import NormalizedRoute

from .geometry import LatLng, bearing_degrees, destination_point, point_at_mile, round_location
from .limits import CORRIDOR_SIDE_OFFSET_MILES, CORRIDOR_SPACING_MILES

# Distance before and after a sample used to measure the local direction of travel.
BEARING_HALF_SPAN_MILES = 0.5

# The route end gets its own mark unless it is closer than this to the previous mark.
MIN_END_MARK_GAP_MILES = 1.0


def corridor_marks(total_miles: float, spacing_miles: float = CORRIDOR_SPACING_MILES) -> list[float]:
    marks = [0.0]
    mark = spacing_miles
    while mark < total_miles:
        marks.append(mark)
        mark += spacing_miles
    if total_miles - marks[-1] >= MIN_END_MARK_GAP_MILES:
        marks.append(total_miles)
    return marks


def route_corridor_points(route: NormalizedRoute) -> list[LatLng]:
    """Centre, left, and right points at each corridor mark of one route."""
    total = route.distance_miles
    points: list[LatLng] = []
    for mark in corridor_marks(total):
        centre = point_at_mile(route.geometry, route.cumulative_miles, mark)
        behind = point_at_mile(route.geometry, route.cumulative_miles, max(0.0, mark - BEARING_HALF_SPAN_MILES))
        ahead = point_at_mile(route.geometry, route.cumulative_miles, min(total, mark + BEARING_HALF_SPAN_MILES))
        points.append(centre)
        if behind == ahead:
            continue
        heading = bearing_degrees(behind, ahead)
        points.append(destination_point(centre, heading - 90, CORRIDOR_SIDE_OFFSET_MILES))
        points.append(destination_point(centre, heading + 90, CORRIDOR_SIDE_OFFSET_MILES))
    return points


def dedupe_locations(points: Iterable[LatLng]) -> list[LatLng]:
    """Round each point for weather lookup and drop repeats, keeping first-seen order."""
    return list(dict.fromkeys(round_location(point) for point in points))


def corridor_points(routes: Sequence[NormalizedRoute]) -> list[LatLng]:
    """Distinct rounded corridor points for all final routes."""
    return dedupe_locations(point for route in routes for point in route_corridor_points(route))


def thin_evenly(points: Sequence[LatLng], limit: int) -> list[LatLng]:
    """Keep at most ``limit`` points, evenly spaced through the list."""
    if limit <= 0:
        return []
    count = len(points)
    if count <= limit:
        return list(points)
    return [points[index * count // limit] for index in range(limit)]
