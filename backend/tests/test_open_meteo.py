from datetime import UTC, datetime, timedelta

import pytest
import requests

from core.cache import TTLCache
from core.errors import ProviderError, ProviderRateLimited, ProviderTimeout
from tests.fakes import FakeResponse, FakeSession
from weather.open_meteo import OpenMeteoWeatherProvider

START = datetime(2026, 11, 3, 16, 0, tzinfo=UTC)
END = START + timedelta(hours=2)
UNITS = {"time": "iso8601", "wind_speed_10m": "mp/h", "rain": "inch", "showers": "inch", "snowfall": "inch"}


def location_body(wind=(11.1, 30.0, None), rain=(0.0, 0.2, 0.1), showers=(0.0, 0.05, None), snow=(0.0, 0.0, 1.5)):
    return {
        "latitude": 32.78,
        "longitude": -96.8,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": dict(UNITS),
        "hourly": {
            "time": ["2026-11-03T16:00", "2026-11-03T17:00", "2026-11-03T18:00"],
            "wind_speed_10m": list(wind),
            "rain": list(rain),
            "showers": list(showers),
            "snowfall": list(snow),
        },
    }


def batch_responder(url, params):
    count = len(params["latitude"].split(","))
    body = [location_body() for _ in range(count)]
    return FakeResponse(200, body[0] if count == 1 else body)


def test_request_uses_explicit_units_and_utc_window():
    session = FakeSession([FakeResponse(200, location_body())])
    OpenMeteoWeatherProvider(session).hourly_forecast([(32.7801, -96.7962)], START + timedelta(minutes=20), END)
    _, params = session.calls[0]
    assert params["hourly"] == "wind_speed_10m,rain,showers,snowfall"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["timezone"] == "GMT"
    assert params["start_hour"] == "2026-11-03T16:00"  # floored to the hour
    assert params["end_hour"] == "2026-11-03T18:00"
    assert (params["latitude"], params["longitude"]) == ("32.78", "-96.80")


def test_weather_mapping_and_units():
    session = FakeSession([FakeResponse(200, location_body())])
    [forecast] = OpenMeteoWeatherProvider(session).hourly_forecast([(32.78, -96.8)], START, END)
    first, second, third = forecast.hours

    assert first.time_utc == datetime(2026, 11, 3, 16, tzinfo=UTC)
    assert second.wind_mph == 30.0
    assert second.rain_in_per_hour == pytest.approx(0.25)  # rain + showers
    assert third.snow_in_per_hour == 1.5
    assert first.is_complete


def test_null_values_stay_missing_and_zero_stays_zero():
    session = FakeSession([FakeResponse(200, location_body())])
    [forecast] = OpenMeteoWeatherProvider(session).hourly_forecast([(32.78, -96.8)], START, END)
    first, _, third = forecast.hours
    assert first.rain_in_per_hour == 0.0 and first.snow_in_per_hour == 0.0
    assert third.wind_mph is None
    assert third.rain_in_per_hour is None  # showers missing -> rain total unknown
    assert not third.is_complete


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b["hourly_units"].update(wind_speed_10m="km/h"),
        lambda b: b["hourly_units"].update(snowfall="cm"),
        lambda b: b["hourly_units"].update(rain="mm"),
        lambda b: b.update(utc_offset_seconds=3600),
        lambda b: b["hourly"].update(rain=[0.0]),
        lambda b: b["hourly"].update(time=["03/11/2026 16:00", "x", "y"]),
        lambda b: b["hourly"].update(snowfall=["a", 0, 0]),
        lambda b: b.pop("hourly"),
    ],
)
def test_unexpected_units_or_shape_is_provider_error(mutate):
    body = location_body()
    mutate(body)
    with pytest.raises(ProviderError):
        OpenMeteoWeatherProvider(FakeSession([FakeResponse(200, body)])).hourly_forecast([(32.78, -96.8)], START, END)


def test_locations_are_batched():
    session = FakeSession(responder=batch_responder)
    locations = [(30 + i * 0.05, -100 + i * 0.05) for i in range(250)]
    forecasts = OpenMeteoWeatherProvider(session).hourly_forecast(locations, START, END)
    assert [len(params["latitude"].split(",")) for _, params in session.calls] == [100, 100, 50]
    assert len(forecasts) == 250
    assert [(f.lat, f.lng) for f in forecasts] == [(round(a, 2), round(b, 2)) for a, b in locations]


def test_identical_rounded_coordinates_are_requested_once():
    session = FakeSession(responder=batch_responder)
    locations = [(32.001, -97.004), (32.0049, -96.9951), (33.0, -97.0), (32.0, -97.0)]
    forecasts = OpenMeteoWeatherProvider(session).hourly_forecast(locations, START, END)
    _, params = session.calls[0]
    assert params["latitude"] == "32.00,33.00"
    assert params["longitude"] == "-97.00,-97.00"
    assert len(forecasts) == 4
    assert forecasts[0].hours == forecasts[1].hours == forecasts[3].hours


def test_cached_locations_are_not_requested_again():
    session = FakeSession(responder=batch_responder)
    provider = OpenMeteoWeatherProvider(session, cache=TTLCache(60))
    provider.hourly_forecast([(32.0, -97.0), (33.0, -97.0)], START, END)
    provider.hourly_forecast([(33.0, -97.0), (34.0, -97.0)], START, END)
    assert [params["latitude"] for _, params in session.calls] == ["32.00,33.00", "34.00"]
    provider.hourly_forecast([(32.0, -97.0), (34.0, -97.0)], START, END)
    assert len(session.calls) == 2


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (FakeResponse(429, {"error": True, "reason": "Minutely API request limit exceeded"}), ProviderRateLimited),
        (requests.Timeout(), ProviderTimeout),
        (FakeResponse(400, {"error": True, "reason": "Parameter start_hour is out of range"}), ProviderError),
        (FakeResponse(200, [location_body(), location_body()]), ProviderError),  # count mismatch
        (FakeResponse(200), ProviderError),
    ],
)
def test_failures_map_to_stable_errors(reply, error):
    with pytest.raises(error):
        OpenMeteoWeatherProvider(FakeSession([reply])).hourly_forecast([(32.78, -96.8)], START, END)


def test_naive_window_rejected():
    with pytest.raises(ValueError):
        OpenMeteoWeatherProvider(FakeSession()).hourly_forecast([(32.78, -96.8)], datetime(2026, 11, 3), END)
