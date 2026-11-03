import math

from analysis.geometry import cumulative_miles, haversine_miles
from analysis.route_similarity import are_duplicates, sample_points, shared_fraction

MILES_PER_DEGREE_LAT = 69.09


def north(start, miles, step_miles=1.0):
    """A straight route north from ``start`` for ``miles``."""
    steps = int(miles / step_miles)
    return [(start[0] + i * step_miles / MILES_PER_DEGREE_LAT, start[1]) for i in range(steps + 1)]


def shift_east(points, miles):
    return [(lat, lng + miles / (69.17 * math.cos(math.radians(lat)))) for lat, lng in points]


def samples(points):
    return sample_points(points, cumulative_miles(points))


BASE = north((32.0, -97.0), 100)


def test_samples_are_evenly_spaced_and_include_both_ends():
    points = samples(BASE)
    assert points[0] == BASE[0]
    assert points[-1] == BASE[-1]
    gaps = [haversine_miles(a, b) for a, b in zip(points, points[1:])]
    assert max(gaps) <= 0.25 + 1e-6


def test_identical_routes_are_duplicates():
    assert are_duplicates(samples(BASE), samples(list(BASE)))


def test_routes_a_third_of_a_mile_apart_are_duplicates():
    assert are_duplicates(samples(BASE), samples(shift_east(BASE, 0.3)))


def test_routes_two_miles_apart_are_distinct():
    other = samples(shift_east(BASE, 2.0))
    assert shared_fraction(samples(BASE), other) == 0
    assert not are_duplicates(samples(BASE), other)


def test_route_sharing_95_percent_of_another_is_a_duplicate():
    # Same first 95 miles, then 5 miles east: 95% of its samples lie on the base route.
    shared = north((32.0, -97.0), 95)
    end = shared[-1]
    detour = shared + [(end[0], end[1] + 5 / (69.17 * math.cos(math.radians(end[0]))))]
    assert are_duplicates(samples(BASE), samples(detour))


def test_route_sharing_80_percent_is_distinct_in_both_directions():
    shared = north((32.0, -97.0), 80)
    end = shared[-1]
    branch = shared + [(end[0], end[1] + 20 / (69.17 * math.cos(math.radians(end[0]))))]
    a, b = samples(BASE), samples(branch)
    assert shared_fraction(a, b) < 0.9
    assert shared_fraction(b, a) < 0.9
    assert not are_duplicates(a, b)


def test_short_route_contained_in_long_route_is_a_duplicate():
    # Either direction reaching 90% is enough.
    short = north((32.0, -97.0), 30)
    a, b = samples(BASE), samples(short)
    assert shared_fraction(a, b) < 0.9
    assert shared_fraction(b, a) == 1.0
    assert are_duplicates(a, b)


def test_empty_samples_share_nothing():
    assert shared_fraction([], samples(BASE)) == 0.0
    assert shared_fraction(samples(BASE), []) == 0.0
