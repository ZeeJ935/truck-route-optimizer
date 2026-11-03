import pytest

from analysis.budget import plan_weather_locations
from analysis.corridor import thin_evenly
from analysis.limits import (
    CORRIDOR_MAX_POINTS,
    CORRIDOR_MIN_RESERVED_POINTS,
    MAX_CHECKPOINT_LOCATIONS,
    MAX_WEATHER_LOCATIONS_PER_ANALYSIS,
)
from core.errors import ValidationFailed


def grid(count, lat0=30.0, lng0=-100.0):
    """``count`` distinct points, already on the rounding grid."""
    return [(round(lat0 + (i // 100) * 0.1, 2), round(lng0 + (i % 100) * 0.1, 2)) for i in range(count)]


CORRIDOR = grid(1_000, lat0=40.0)


def test_limits_match_the_rule():
    assert MAX_WEATHER_LOCATIONS_PER_ANALYSIS == 550
    assert CORRIDOR_MIN_RESERVED_POINTS == 100
    assert CORRIDOR_MAX_POINTS == 250
    assert MAX_CHECKPOINT_LOCATIONS == 450


def test_checkpoints_shared_by_routes_are_deduplicated_first():
    route_a = grid(300)
    route_b = route_a[:200] + grid(100, lat0=35.0)  # shares 200 of its 300 checkpoints with route A
    # 600 raw checkpoints would be rejected; 400 distinct fit.
    budget = plan_weather_locations(route_a + route_b, CORRIDOR, 10)
    assert len(budget.checkpoint_locations) == 400
    assert budget.corridor_budget == 150


def test_dedup_lets_a_trip_fit_that_would_not_fit_without_it():
    shared = grid(300)
    budget = plan_weather_locations(shared + shared, CORRIDOR, 10)  # 600 raw, 300 distinct
    assert len(budget.checkpoint_locations) == 300


def test_nearby_points_rounding_to_the_same_location_count_once():
    budget = plan_weather_locations([(32.001, -97.004), (32.004, -96.996)], CORRIDOR, 25)
    assert budget.checkpoint_locations == ((32.0, -97.0),)


@pytest.mark.parametrize(
    ("checkpoints", "corridor_budget"),
    [(10, 250), (200, 250), (300, 250), (301, 249), (350, 200), (449, 101), (450, 100)],
)
def test_leftover_budget_goes_to_the_corridor_up_to_250(checkpoints, corridor_budget):
    budget = plan_weather_locations(grid(checkpoints), CORRIDOR, 10)
    assert budget.corridor_budget == corridor_budget
    assert len(budget.corridor_locations) == corridor_budget
    assert len(budget.checkpoint_locations) + len(budget.corridor_locations) <= MAX_WEATHER_LOCATIONS_PER_ANALYSIS


def test_at_least_100_corridor_locations_are_always_reserved():
    budget = plan_weather_locations(grid(450), CORRIDOR, 10)
    assert len(budget.corridor_locations) == 100


def test_small_corridor_is_kept_whole():
    corridor = grid(40, lat0=45.0)
    budget = plan_weather_locations(grid(50), corridor, 25)
    assert list(budget.corridor_locations) == corridor


@pytest.mark.parametrize(
    ("interval", "suggestion"),
    [(10, "Choose a larger sampling interval (25 or 50 miles)."), (25, "Choose a larger sampling interval (50 miles).")],
)
def test_too_many_checkpoints_rejects_and_suggests_a_larger_interval(interval, suggestion):
    with pytest.raises(ValidationFailed) as raised:
        plan_weather_locations(grid(451), CORRIDOR, interval)
    assert raised.value.code == "validation_error"
    assert "451 weather checkpoints" in raised.value.message
    assert raised.value.message.endswith(suggestion)
    assert "sampling_interval_miles" in raised.value.fields


def test_too_many_checkpoints_at_the_largest_interval_says_the_trip_is_too_long():
    with pytest.raises(ValidationFailed) as raised:
        plan_weather_locations(grid(451), CORRIDOR, 50)
    assert "too long to analyze" in raised.value.message


def test_checkpoints_are_never_dropped():
    checkpoints = grid(450)
    budget = plan_weather_locations(checkpoints, CORRIDOR, 10)
    assert list(budget.checkpoint_locations) == checkpoints


def test_corridor_points_matching_checkpoints_cost_no_extra_location():
    checkpoints = grid(100)
    corridor = checkpoints[:50] + grid(50, lat0=45.0)
    budget = plan_weather_locations(checkpoints, corridor, 25)
    assert len(budget.corridor_locations) == 100
    assert len(budget.all_locations) == 150


def test_thinning_is_even():
    points = grid(1_000)
    kept = thin_evenly(points, 250)
    assert kept == points[::4]
    assert thin_evenly(points[:10], 250) == points[:10]
    assert thin_evenly(points, 0) == []
