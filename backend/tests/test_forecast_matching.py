from datetime import UTC, datetime, timedelta, timezone

import pytest

from analysis.forecast_matching import match_forecast_hour


def at(hour, minute=0):
    return datetime(2026, 11, 3, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("target", "hours", "expected"),
    [
        (at(10, 29), [at(10), at(11)], at(10)),
        (at(10, 30), [at(10), at(11)], at(10)),
        (at(10, 31), [at(10), at(11)], at(11)),
        (at(10, 31), [at(10), at(12)], None),
    ],
)
def test_spec_examples(target, hours, expected):
    assert match_forecast_hour(target, hours) == expected


def test_tie_prefers_earlier_hour_regardless_of_input_order():
    assert match_forecast_hour(at(10, 30), [at(11), at(10)]) == at(10)


def test_exact_hour_matches_itself():
    assert match_forecast_hour(at(10), [at(9), at(10), at(11)]) == at(10)


def test_window_boundary_is_inclusive():
    target = at(10, 30)
    assert match_forecast_hour(target, [at(11)]) == at(11)
    assert match_forecast_hour(target + timedelta(seconds=1), [at(10)]) is None


def test_no_hours_means_no_forecast():
    assert match_forecast_hour(at(10), []) is None


def test_offsets_are_compared_as_instants():
    plus_five = timezone(timedelta(hours=5))
    target = datetime(2026, 11, 3, 15, 20, tzinfo=plus_five)  # 10:20 UTC
    assert match_forecast_hour(target, [at(10), at(11)]) == at(10)


def test_naive_datetimes_rejected():
    with pytest.raises(ValueError):
        match_forecast_hour(datetime(2026, 11, 3, 10), [at(10)])
    with pytest.raises(ValueError):
        match_forecast_hour(at(10), [datetime(2026, 11, 3, 10)])
