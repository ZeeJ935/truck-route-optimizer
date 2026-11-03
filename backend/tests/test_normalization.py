import math
from datetime import UTC, datetime, timedelta

import pytest

from analysis.checkpoints import place_checkpoints
from analysis.eta import eta_at_mile
from analysis.geometry import cumulative_miles
from core.errors import ProviderError
from routing.normalization import normalize_route

# A straight route north along a meridian. Its haversine length is about 100 miles.
GEOMETRY = [(32.0 + i * (100 / 69.09) / 50, -97.0) for i in range(51)]
GEOMETRY_MILES = cumulative_miles(GEOMETRY)[-1]
PROVIDER_MILES = 103.0  # The provider's road length differs from the geometry length.
PROVIDER_SECONDS = 3_700.0
PROGRESS = [(0.0, 0.0), (50.5, 1_800.0), (101.0, 3_600.0)]  # Ends at 101 mi / 3,600 s.


def test_fixture_lengths_really_differ():
    assert math.isclose(GEOMETRY_MILES, 100.0, abs_tol=0.1)
    assert PROGRESS[-1][0] != PROVIDER_MILES


def test_everything_uses_the_provider_length_as_total():
    route = normalize_route(GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, PROGRESS, "provider")

    assert route.distance_miles == PROVIDER_MILES
    assert route.cumulative_miles[0] == 0
    assert route.cumulative_miles[-1] == PROVIDER_MILES
    assert len(route.cumulative_miles) == len(route.geometry)
    assert route.progress[-1].miles == PROVIDER_MILES
    assert route.progress[-1].seconds == PROVIDER_SECONDS

    # Interior values are scaled proportionally.
    scale = PROVIDER_MILES / GEOMETRY_MILES
    assert math.isclose(route.cumulative_miles[25], cumulative_miles(GEOMETRY)[25] * scale)
    assert math.isclose(route.progress[1].miles, 50.5 * PROVIDER_MILES / 101.0)
    assert math.isclose(route.progress[1].seconds, 1_800.0 * PROVIDER_SECONDS / 3_600.0)


def test_checkpoints_segments_and_etas_share_the_basis():
    route = normalize_route(GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, PROGRESS, "provider")
    placements = place_checkpoints(route.geometry, route.cumulative_miles, 25)

    assert [p.mile for p in placements] == [0, 25, 50, 75, 100, 103.0]
    assert math.isclose(sum(p.segment_miles for p in placements), PROVIDER_MILES, abs_tol=1e-9)
    assert (placements[-1].lat, placements[-1].lng) == GEOMETRY[-1]

    departure = datetime(2026, 11, 3, 3, 0, tzinfo=UTC)
    assert eta_at_mile(departure, route.progress, placements[-1].mile) == departure + timedelta(
        seconds=PROVIDER_SECONDS
    )
    # Mile 51.5 on the provider basis is the scaled middle progress entry.
    mid_eta = eta_at_mile(departure, route.progress, 50.5 * PROVIDER_MILES / 101.0)
    assert mid_eta == departure + timedelta(seconds=1_800.0 * PROVIDER_SECONDS / 3_600.0)


def test_checkpoint_on_scaled_basis_sits_at_matching_fraction_of_geometry():
    route = normalize_route(GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, PROGRESS, "provider")
    placements = place_checkpoints(route.geometry, route.cumulative_miles, 50)
    # Provider mile 50 of 103 is 50/103 of the way along the geometry.
    expected_lat = GEOMETRY[0][0] + (GEOMETRY[-1][0] - GEOMETRY[0][0]) * 50 / 103
    assert math.isclose(placements[1].lat, expected_lat, abs_tol=1e-9)


@pytest.mark.parametrize(
    ("points", "distance", "duration", "progress"),
    [
        (GEOMETRY[:1], PROVIDER_MILES, PROVIDER_SECONDS, PROGRESS),
        (GEOMETRY, 0, PROVIDER_SECONDS, PROGRESS),
        (GEOMETRY, PROVIDER_MILES, 0, PROGRESS),
        (GEOMETRY, math.nan, PROVIDER_SECONDS, PROGRESS),
        (GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, []),
        (GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, [(0.0, 0.0)]),
        (GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, [(1.0, 0.0), (101.0, 3_600.0)]),
        (GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, [(0.0, 0.0), (60.0, 2_000.0), (50.0, 3_600.0)]),
        (GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, [(0.0, 0.0), (60.0, 2_000.0), (101.0, 1_000.0)]),
        (GEOMETRY, PROVIDER_MILES, PROVIDER_SECONDS, [(0.0, 0.0), (0.0, 0.0)]),
        ([(32.0, -97.0), (32.0, -97.0)], PROVIDER_MILES, PROVIDER_SECONDS, PROGRESS),
    ],
)
def test_malformed_route_data_is_a_provider_error(points, distance, duration, progress):
    with pytest.raises(ProviderError):
        normalize_route(points, distance, duration, progress, "provider")
