import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from analysis.eta import ProgressPoint, eta_at_mile, travel_seconds_at_mile
from analysis.geometry import cumulative_miles, haversine_miles, point_at_mile


def test_haversine_known_distance():
    # One degree of latitude is about 69.09 miles.
    assert math.isclose(haversine_miles((32.0, -97.0), (33.0, -97.0)), 69.09, abs_tol=0.01)
    assert haversine_miles((32.0, -97.0), (32.0, -97.0)) == 0


def test_cumulative_and_point_at_mile():
    polyline = [(32.0, -97.0), (33.0, -97.0), (34.0, -97.0)]
    cumulative = cumulative_miles(polyline)
    assert cumulative[0] == 0
    assert math.isclose(cumulative[2], 2 * cumulative[1])

    mid = point_at_mile(polyline, cumulative, cumulative[1] / 2)
    assert math.isclose(mid[0], 32.5) and mid[1] == -97.0
    assert point_at_mile(polyline, cumulative, 0) == polyline[0]
    assert point_at_mile(polyline, cumulative, cumulative[-1]) == polyline[-1]
    assert point_at_mile(polyline, cumulative, cumulative[1]) == polyline[1]


def test_cumulative_needs_two_points():
    with pytest.raises(ValueError):
        cumulative_miles([(32.0, -97.0)])


PROGRESS = [
    ProgressPoint(0, 0),
    ProgressPoint(10, 600),  # 60 mph
    ProgressPoint(30, 2_400),  # 40 mph on this stretch
    ProgressPoint(30, 2_700),  # stopped in traffic: distance unchanged, time grows
    ProgressPoint(50, 3_900),
]


@pytest.mark.parametrize(
    ("mile", "seconds"),
    [(0, 0), (5, 300), (10, 600), (20, 1_500), (40, 3_300), (50, 3_900)],
)
def test_travel_time_interpolates_within_bracketing_entries(mile, seconds):
    assert math.isclose(travel_seconds_at_mile(PROGRESS, mile), seconds)


def test_eta_is_utc_and_uses_departure_offset():
    departure = datetime(2026, 11, 3, 8, 0, tzinfo=timezone(timedelta(hours=5)))
    eta = eta_at_mile(departure, PROGRESS, 10)
    assert eta.tzinfo == UTC
    assert eta == datetime(2026, 11, 3, 3, 10, tzinfo=UTC)


def test_eta_with_z_departure():
    departure = datetime(2026, 11, 3, 3, 0, tzinfo=UTC)
    assert eta_at_mile(departure, PROGRESS, 50) == datetime(2026, 11, 3, 4, 5, tzinfo=UTC)


def test_eta_rejects_naive_departure():
    with pytest.raises(ValueError):
        eta_at_mile(datetime(2026, 11, 3, 8, 0), PROGRESS, 10)


@pytest.mark.parametrize("mile", [-0.1, 50.1])
def test_eta_rejects_mile_outside_route(mile):
    with pytest.raises(ValueError):
        travel_seconds_at_mile(PROGRESS, mile)


@pytest.mark.parametrize(
    "progress",
    [
        [ProgressPoint(0, 0)],
        [ProgressPoint(1, 0), ProgressPoint(2, 60)],
        [ProgressPoint(0, 0), ProgressPoint(10, 600), ProgressPoint(5, 700)],
        [ProgressPoint(0, 0), ProgressPoint(10, 600), ProgressPoint(20, 500)],
    ],
)
def test_invalid_progress_rejected(progress):
    with pytest.raises(ValueError):
        travel_seconds_at_mile(progress, 0)
