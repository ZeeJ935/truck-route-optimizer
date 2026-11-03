import math
from datetime import UTC, datetime, timedelta

from analysis.corridor import corridor_marks, corridor_points, route_corridor_points
from analysis.forecast_window import forecast_horizon_end, slider_timestamps, weather_window
from analysis.geometry import bearing_degrees, destination_point, haversine_miles
from tests.fakes import make_route

MILES_PER_DEGREE_LAT = 69.09
NORTH_100 = make_route([(32.0 + i / MILES_PER_DEGREE_LAT, -97.0) for i in range(101)], 3_600)


def test_marks_every_25_miles_including_both_ends():
    assert corridor_marks(100) == [0, 25, 50, 75, 100]
    assert corridor_marks(60) == [0, 25, 50, 60]
    assert corridor_marks(20) == [0, 20]


def test_centre_and_side_points():
    points = route_corridor_points(NORTH_100)
    assert len(points) == 15  # 5 marks x (centre, left, right)
    for index in range(0, 15, 3):
        centre, left, right = points[index : index + 3]
        assert math.isclose(haversine_miles(centre, left), 10, rel_tol=1e-6)
        assert math.isclose(haversine_miles(centre, right), 10, rel_tol=1e-6)
        # Route runs north, so side points are due west and east of the centre.
        assert math.isclose(left[0], centre[0], abs_tol=0.01) and left[1] < centre[1]
        assert math.isclose(right[0], centre[0], abs_tol=0.01) and right[1] > centre[1]


def test_centres_are_25_miles_apart_along_the_route():
    centres = route_corridor_points(NORTH_100)[::3]
    gaps = [haversine_miles(a, b) for a, b in zip(centres, centres[1:])]
    assert all(math.isclose(gap, 25, rel_tol=0.01) for gap in gaps)


def test_points_shared_between_routes_are_deduplicated():
    # Two routes sharing their first 50 miles share all points at marks 0 and 25 (6 points)
    # and the centre at mark 50; the side points at 50 differ because the routes branch there.
    shared = [(32.0 + i / MILES_PER_DEGREE_LAT, -97.0) for i in range(51)]
    branch_east = make_route(shared + [(shared[-1][0] + 0.5, -96.0)], 3_000)
    branch_west = make_route(shared + [(shared[-1][0] + 0.5, -98.0)], 3_000)
    separate = len(route_corridor_points(branch_east)) + len(route_corridor_points(branch_west))
    combined = corridor_points([branch_east, branch_west])
    assert len(combined) == len(set(combined))
    assert len(combined) == separate - 7


def test_bearing_and_destination_point():
    assert math.isclose(bearing_degrees((32, -97), (33, -97)), 0, abs_tol=1e-9)
    assert math.isclose(bearing_degrees((32, -97), (32, -96)), 89.7, abs_tol=0.1)
    end = destination_point((32, -97), 90, 50)
    assert math.isclose(haversine_miles((32, -97), end), 50, rel_tol=1e-9)


# --- Forecast window --------------------------------------------------------------

DEPARTURE = datetime(2026, 11, 3, 3, 10, tzinfo=UTC)
NOW = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)


def test_horizon_is_last_hour_of_day_16():
    assert forecast_horizon_end(NOW) == datetime(2026, 11, 18, 23, 0, tzinfo=UTC)


def test_window_covers_slider_when_trip_is_short():
    start, end = weather_window(DEPARTURE, DEPARTURE + timedelta(hours=5), forecast_horizon_end(NOW))
    assert start == datetime(2026, 11, 3, 2, 0, tzinfo=UTC)  # departure - 30 min, floored
    assert end == datetime(2026, 11, 5, 4, 0, tzinfo=UTC)  # departure + 48 h + 30 min, ceiled


def test_window_covers_eta_beyond_48_hours():
    latest_eta = DEPARTURE + timedelta(hours=60, minutes=20)  # 2026-11-05T15:30Z
    start, end = weather_window(DEPARTURE, latest_eta, forecast_horizon_end(NOW))
    assert end == datetime(2026, 11, 5, 16, 0, tzinfo=UTC)
    assert end - start > timedelta(hours=48)


def test_window_is_clamped_to_the_provider_horizon():
    late_departure = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    _, end = weather_window(late_departure, late_departure + timedelta(hours=3), forecast_horizon_end(NOW))
    assert end == datetime(2026, 11, 18, 23, 0, tzinfo=UTC)


def test_slider_hour_zero_is_departure_and_hour_n_is_departure_plus_n_hours():
    stamps = slider_timestamps(datetime(2026, 11, 3, 8, 10, tzinfo=UTC) - timedelta(hours=5))
    assert len(stamps) == 49
    assert stamps[0] == datetime(2026, 11, 3, 3, 10, tzinfo=UTC)
    assert all(stamps[n] == stamps[0] + timedelta(hours=n) for n in range(49))
