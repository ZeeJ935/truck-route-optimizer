import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from analysis.request import parse_analysis_request
from core.errors import ValidationFailed

NOW = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)


def clock():
    return NOW


def payload(**overrides):
    body = {
        "origin": "Dallas, TX",
        "destination": "Denver, CO",
        "departure_time": "2026-11-03T08:00:00+05:00",
        "load_weight_lb": 40000,
        "sampling_interval_miles": 25,
    }
    body.update(overrides)
    return body


def field_error(body):
    with pytest.raises(ValidationFailed) as raised:
        parse_analysis_request(body, clock)
    assert raised.value.code == "validation_error"
    return raised.value.fields


def test_valid_request():
    request = parse_analysis_request(payload(origin="  Dallas,   TX "), clock)
    assert request.origin == "Dallas, TX"
    assert request.destination == "Denver, CO"
    assert request.load_weight_lb == 40000.0
    assert request.sampling_interval_miles == 25


def test_plus_five_offset_is_kept_and_converted_to_utc():
    request = parse_analysis_request(payload(departure_time="2026-11-03T08:00:00+05:00"), clock)
    assert request.departure.utcoffset() == timedelta(hours=5)
    assert request.departure_utc == datetime(2026, 11, 3, 3, 0, tzinfo=UTC)


def test_z_timestamp_is_accepted_as_utc():
    request = parse_analysis_request(payload(departure_time="2026-11-03T03:00:00Z"), clock)
    assert request.departure_utc == datetime(2026, 11, 3, 3, 0, tzinfo=UTC)


@pytest.mark.parametrize("value", ["2026-11-03T08:00:00", "2026-11-03T08:00", "2026-11-03"])
def test_offset_less_timestamp_is_rejected(value):
    assert "offset" in field_error(payload(departure_time=value))["departure_time"]


@pytest.mark.parametrize("value", ["tomorrow", "2026-13-03T08:00:00Z", "", 12345, None])
def test_unparseable_departure_is_rejected(value):
    assert "departure_time" in field_error(payload(departure_time=value))


def test_departure_more_than_five_minutes_in_the_past_is_rejected():
    six_minutes_ago = (NOW - timedelta(minutes=6)).isoformat()
    assert "past" in field_error(payload(departure_time=six_minutes_ago))["departure_time"]


@pytest.mark.parametrize("minutes", [5, 4, 0])
def test_departure_inside_the_grace_period_is_accepted(minutes):
    departure = NOW - timedelta(minutes=minutes)
    assert parse_analysis_request(payload(departure_time=departure.isoformat()), clock).departure == departure


def test_grace_period_applies_to_the_instant_not_the_wall_clock():
    # 06:56 at +05:00 is 01:56 UTC: 4 minutes before NOW, so it is accepted.
    local = datetime(2026, 11, 3, 6, 56, tzinfo=timezone(timedelta(hours=5)))
    assert parse_analysis_request(payload(departure_time=local.isoformat()), clock).departure == local


def test_departure_beyond_forecast_range_is_rejected():
    # Forecasts reach the last hour of day 16 counted from today 00:00 UTC.
    last_hour = datetime(2026, 11, 18, 23, 0, tzinfo=UTC)
    assert parse_analysis_request(payload(departure_time=last_hour.isoformat()), clock)
    too_late = (last_hour + timedelta(minutes=1)).isoformat()
    assert "forecast range" in field_error(payload(departure_time=too_late))["departure_time"]


@pytest.mark.parametrize("value", [5, 15, 100, 25.5, 25.0, "25", True, None])
def test_invalid_interval_is_rejected(value):
    assert "sampling_interval_miles" in field_error(payload(sampling_interval_miles=value))


@pytest.mark.parametrize("value", [10, 25, 50])
def test_each_allowed_interval_is_accepted(value):
    assert parse_analysis_request(payload(sampling_interval_miles=value), clock).sampling_interval_miles == value


@pytest.mark.parametrize("value", [0, -1, -0.5, math.nan, math.inf, "40000", True, None, [40000]])
def test_invalid_load_is_rejected(value):
    assert "load_weight_lb" in field_error(payload(load_weight_lb=value))


@pytest.mark.parametrize("value", [0.1, 1, 40000, 80000.5])
def test_positive_load_is_accepted(value):
    assert parse_analysis_request(payload(load_weight_lb=value), clock).load_weight_lb == float(value)


@pytest.mark.parametrize(
    "field", ["origin", "destination", "departure_time", "load_weight_lb", "sampling_interval_miles"]
)
def test_missing_field_is_rejected(field):
    body = payload()
    del body[field]
    assert field in field_error(body)


@pytest.mark.parametrize("value", ["", "   ", 42, None])
def test_blank_place_is_rejected(value):
    assert "origin" in field_error(payload(origin=value))


def test_overlong_place_is_rejected():
    assert "destination" in field_error(payload(destination="x" * 201))


def test_all_field_errors_are_reported_together():
    errors = field_error({"origin": "", "load_weight_lb": -1})
    assert set(errors) == {"origin", "destination", "departure_time", "load_weight_lb", "sampling_interval_miles"}


@pytest.mark.parametrize("body", [[], "text", None, 42])
def test_non_object_body_is_rejected(body):
    with pytest.raises(ValidationFailed):
        parse_analysis_request(body, clock)


def test_unknown_fields_are_ignored():
    request = parse_analysis_request(payload(provider="fake", use_fakes=True), clock)
    assert not hasattr(request, "provider")
