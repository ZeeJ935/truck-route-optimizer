import math
from datetime import UTC, datetime

import pytest

from analysis.geometry import haversine_miles
from analysis.route_selection import route_notice, select_routes, via_points
from core.errors import NoRouteFound, ProviderError, ProviderRateLimited, ProviderTimeout
from tests.fakes import FakeRoutingProvider, make_route

ORIGIN = (32.0, -97.0)
DESTINATION = (33.5, -97.0)
DEPARTURE = datetime(2026, 11, 3, 3, 0, tzinfo=UTC)


def bulge(lng, offset=0.0):
    """A route from ORIGIN to DESTINATION through (32.75, lng), optionally shifted east by `offset` degrees."""
    return [(ORIGIN[0], ORIGIN[1] + offset), (32.75, lng + offset), (DESTINATION[0], DESTINATION[1] + offset)]


STRAIGHT = [ORIGIN, DESTINATION]
EAST = bulge(-96.6)
WEST = bulge(-97.4)
FAR_EAST = bulge(-96.2)
FAR_WEST = bulge(-97.8)


def run(provider):
    return select_routes(provider, ORIGIN, DESTINATION, DEPARTURE, 40_000)


def geometries(selection):
    return [route.geometry for route in selection.routes]


def test_three_distinct_routes_return_three_without_fallback():
    provider = FakeRoutingProvider([make_route(STRAIGHT, 100), make_route(EAST, 110), make_route(WEST, 120)])
    selection = run(provider)
    assert geometries(selection) == [tuple(STRAIGHT), tuple(EAST), tuple(WEST)]
    assert selection.notice is None
    assert selection.provider_route_count == 3
    assert not selection.used_fallback
    assert provider.calls == [{"max_alternatives": 2, "via": ()}]


def test_duplicates_with_different_sources_are_removed_keeping_the_faster():
    # Nearly the same road (shifted ~0.2 mi) returned twice; the slower copy comes first.
    near_copy = bulge(-96.6, offset=0.003)
    slow = make_route(EAST, 130, source="provider")
    fast = make_route(near_copy, 105, source="via")
    provider = FakeRoutingProvider([slow, make_route(STRAIGHT, 100)], via_responses=[[fast]])
    selection = run(provider)
    assert tuple(near_copy) in geometries(selection)
    assert tuple(EAST) not in geometries(selection)
    assert len(selection.routes) == 2


def test_clearly_different_routes_stay_separate():
    provider = FakeRoutingProvider([make_route(EAST, 100), make_route(WEST, 100), make_route(STRAIGHT, 100)])
    assert len(run(provider).routes) == 3


def test_via_route_slower_than_one_and_a_half_times_is_rejected():
    provider = FakeRoutingProvider(
        [make_route(STRAIGHT, 100), make_route(EAST, 120)],
        via_responses=[[make_route(WEST, 150.01)], [make_route(FAR_WEST, 150)]],
    )
    selection = run(provider)
    assert [route.duration_seconds for route in selection.routes] == [100, 120, 150]
    assert tuple(WEST) not in geometries(selection)
    assert selection.via_attempts == 2


def test_via_fallback_runs_until_three_routes():
    provider = FakeRoutingProvider(
        [make_route(STRAIGHT, 100)],
        via_responses=[[make_route(EAST, 110)], [make_route(WEST, 115)], [make_route(FAR_EAST, 101)]],
    )
    selection = run(provider)
    assert len(selection.routes) == 3
    assert selection.via_attempts == 2  # stops as soon as three remain
    assert all(call["max_alternatives"] == 0 and len(call["via"]) == 1 for call in provider.calls[1:])
    assert selection.notice is None


def test_via_duplicate_of_existing_route_does_not_count():
    provider = FakeRoutingProvider(
        [make_route(STRAIGHT, 100), make_route(EAST, 110)],
        via_responses=[[make_route(bulge(-96.6, 0.002), 140)], [make_route(WEST, 120)]],
    )
    selection = run(provider)
    assert geometries(selection) == [tuple(STRAIGHT), tuple(EAST), tuple(WEST)]


@pytest.mark.parametrize(
    ("primary", "count", "notice"),
    [
        ([STRAIGHT, EAST], 2, "Only 2 distinct routes were available for this trip."),
        ([STRAIGHT], 1, "Only 1 distinct route was available for this trip."),
    ],
)
def test_fewer_routes_are_returned_honestly_with_a_notice(primary, count, notice):
    routes = [make_route(points, 100 + index) for index, points in enumerate(primary)]
    provider = FakeRoutingProvider(routes, via_responses=[NoRouteFound()] * 4)
    selection = run(provider)
    assert len(selection.routes) == count
    assert selection.notice == notice
    assert selection.via_attempts == 4
    # Nothing is duplicated to fill the gap.
    assert len(set(geometries(selection))) == count


def test_more_than_three_acceptable_routes_keep_the_three_fastest():
    provider = FakeRoutingProvider(
        [make_route(FAR_EAST, 140), make_route(STRAIGHT, 100), make_route(WEST, 120), make_route(EAST, 110)]
    )
    selection = run(provider)
    assert [route.duration_seconds for route in selection.routes] == [100, 110, 120]


def test_slow_provider_route_is_filtered_before_counting():
    provider = FakeRoutingProvider(
        [make_route(STRAIGHT, 100), make_route(EAST, 200), make_route(WEST, 110)],
        via_responses=[[make_route(FAR_WEST, 130)]],
    )
    selection = run(provider)
    assert [route.duration_seconds for route in selection.routes] == [100, 110, 130]


def test_no_routes_at_all_is_no_route_found():
    with pytest.raises(NoRouteFound):
        run(FakeRoutingProvider(NoRouteFound()))


@pytest.mark.parametrize("error", [ProviderTimeout(), ProviderRateLimited(), ProviderError()])
def test_provider_failures_propagate_from_primary_request(error):
    with pytest.raises(type(error)):
        run(FakeRoutingProvider(error))


@pytest.mark.parametrize("error", [ProviderTimeout(), ProviderError()])
def test_failed_via_attempt_is_logged_skipped_and_accepted_routes_kept(error, caplog):
    provider = FakeRoutingProvider(
        [make_route(STRAIGHT, 100)],
        via_responses=[error, [make_route(EAST, 110)], [make_route(WEST, 120)]],
    )
    selection = run(provider)
    assert geometries(selection) == [tuple(STRAIGHT), tuple(EAST), tuple(WEST)]
    assert selection.via_attempts == 3  # the failed attempt is skipped, later ones still run
    assert f"failed ({error.code})" in caplog.text


@pytest.mark.parametrize("error", [ProviderTimeout(), ProviderError()])
def test_every_via_attempt_failing_still_returns_accepted_routes(error):
    provider = FakeRoutingProvider([make_route(STRAIGHT, 100), make_route(EAST, 110)], via_responses=[error] * 4)
    selection = run(provider)
    assert len(selection.routes) == 2
    assert selection.notice == "Only 2 distinct routes were available for this trip."


def test_rate_limited_via_attempt_stops_further_via_requests(caplog):
    provider = FakeRoutingProvider(
        [make_route(STRAIGHT, 100)],
        via_responses=[[make_route(EAST, 110)], ProviderRateLimited(), [make_route(WEST, 120)]],
    )
    selection = run(provider)
    assert geometries(selection) == [tuple(STRAIGHT), tuple(EAST)]
    assert selection.via_attempts == 2
    assert len(provider.calls) == 3  # primary + 2 via; no request after the rate limit
    assert "rate limited" in caplog.text


def test_via_points_are_perpendicular_offsets_from_the_midpoint():
    points = via_points(ORIGIN, DESTINATION, fractions=(0.15, -0.15))
    straight = haversine_miles(ORIGIN, DESTINATION)
    for point in points:
        # Equidistant from both ends, at about 15% of the straight-line distance from the midpoint.
        assert math.isclose(haversine_miles(point, ORIGIN), haversine_miles(point, DESTINATION), rel_tol=1e-3)
        assert math.isclose(haversine_miles(point, (32.75, -97.0)), 0.15 * straight, rel_tol=0.01)
    assert points[0][1] < -97.0 < points[1][1]  # one on each side
    assert via_points(ORIGIN, ORIGIN) == []


def test_route_notice_text():
    assert route_notice(3) is None
    assert route_notice(2) == "Only 2 distinct routes were available for this trip."
    assert route_notice(1) == "Only 1 distinct route was available for this trip."
