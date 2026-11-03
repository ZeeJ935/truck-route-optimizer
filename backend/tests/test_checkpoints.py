import math

import pytest

from analysis.checkpoints import checkpoint_miles, place_checkpoints, segment_miles
from analysis.geometry import cumulative_miles, haversine_miles

INTERVALS = (10, 25, 50)


def _expected_markers(total, interval):
    markers = [0.0]
    mile = interval
    while mile < total:
        markers.append(float(mile))
        mile += interval
    return markers + [float(total)]


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (73, [0, 25, 50, 73]),
        (75, [0, 25, 50, 75]),
        (20, [0, 20]),
    ],
)
def test_spec_examples_at_25_miles(total, expected):
    assert checkpoint_miles(total, 25) == expected


def _cases():
    for interval in INTERVALS:
        yield interval, interval * 0.6, "shorter than interval"
        yield interval, float(interval), "equal to interval"
        yield interval, interval + 0.01, "slightly above interval"
        yield interval, interval * 3.0, "exact multiple"
        yield interval, interval * 3.0 + 0.001, "just above a multiple"
        yield interval, 883.4, "long route"
        yield interval, 2_712.6, "very long route"


@pytest.mark.parametrize(("interval", "total", "case"), list(_cases()))
def test_checkpoint_markers(interval, total, case):
    markers = checkpoint_miles(total, interval)
    assert markers == _expected_markers(total, interval), case
    assert markers[0] == 0
    assert markers[-1] == total
    assert len(set(markers)) == len(markers), "destination must not be duplicated"


@pytest.mark.parametrize(("interval", "total", "case"), list(_cases()))
def test_segment_miles_sum_to_route_length(interval, total, case):
    segments = segment_miles(checkpoint_miles(total, interval))
    assert math.isclose(sum(segments), total, abs_tol=1e-9), case
    assert all(segment > 0 for segment in segments), case


def test_segment_representation_uses_midpoints():
    # 0, 25, 50, 73 -> midpoints 12.5, 37.5, 61.5
    assert segment_miles([0, 25, 50, 73]) == [12.5, 25.0, 24.0, 11.5]
    assert segment_miles([0, 20]) == [10.0, 10.0]


def test_float_noise_just_below_a_multiple_does_not_duplicate_destination():
    assert checkpoint_miles(75 - 1e-9, 25) == [0, 25, 50, 75 - 1e-9]
    assert checkpoint_miles(75 + 1e-9, 25) == [0, 25, 50, 75 + 1e-9]


@pytest.mark.parametrize("interval", [0, 5, 15, 25.5, 100, -10])
def test_invalid_interval_rejected(interval):
    with pytest.raises(ValueError):
        checkpoint_miles(100, interval)


@pytest.mark.parametrize("total", [0, -5, math.nan, math.inf])
def test_invalid_route_length_rejected(total):
    with pytest.raises(ValueError):
        checkpoint_miles(total, 25)


def test_segment_miles_rejects_bad_markers():
    with pytest.raises(ValueError):
        segment_miles([0])
    with pytest.raises(ValueError):
        segment_miles([0, 25, 25])


def _bent_polyline():
    # North along a meridian, then east: a non-straight route of about 200 miles.
    north = [(32.0 + i * 0.05, -97.0) for i in range(30)]
    east = [(north[-1][0], -97.0 + i * 0.05) for i in range(1, 30)]
    return north + east


@pytest.mark.parametrize("interval", INTERVALS)
def test_place_checkpoints_on_route_geometry(interval):
    polyline = _bent_polyline()
    total = cumulative_miles(polyline)[-1]
    placements = place_checkpoints(polyline, cumulative_miles(polyline), interval)

    assert [p.mile for p in placements] == checkpoint_miles(total, interval)
    assert (placements[0].lat, placements[0].lng) == polyline[0]
    assert (placements[-1].lat, placements[-1].lng) == polyline[-1]
    assert math.isclose(sum(p.segment_miles for p in placements), total, abs_tol=1e-9)

    # Each interior checkpoint lies on the polyline: its distance to the nearest
    # vertex pair is consistent with lying on that segment.
    for placement in placements[1:-1]:
        point = (placement.lat, placement.lng)
        on_route = any(
            math.isclose(
                haversine_miles(a, point) + haversine_miles(point, b),
                haversine_miles(a, b),
                abs_tol=1e-3,
            )
            for a, b in zip(polyline, polyline[1:])
        )
        assert on_route, placement


def test_place_checkpoints_mile_matches_distance_along_route():
    polyline = [(32.0 + i * 0.01, -97.0) for i in range(200)]
    placements = place_checkpoints(polyline, cumulative_miles(polyline), 25)
    origin = polyline[0]
    for placement in placements:
        # On a straight meridian, distance from origin equals the mile marker.
        assert math.isclose(haversine_miles(origin, (placement.lat, placement.lng)), placement.mile, abs_tol=1e-6)
