from datetime import UTC, datetime, timedelta, timezone

import pytest

from analysis.limits import MAX_WEATHER_LOCATIONS_PER_ANALYSIS
from analysis.request import AnalysisRequest
from analysis.service import AnalysisService
from core.errors import ForecastUnavailable, ProviderRateLimited, ValidationFailed
from risk.engine import RiskEngine
from tests.fakes import FakeGeocoder, FakeRoutingProvider, FakeWeatherProvider, SpyRiskEngine, make_route

NOW = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
DEPARTURE = datetime(2026, 11, 3, 8, 0, tzinfo=timezone(timedelta(hours=5)))  # 03:00 UTC
DEPARTURE_UTC = DEPARTURE.astimezone(UTC)
ORIGIN = (32.0, -97.0)
DESTINATION = (34.0, -97.0)
LOAD = 40_000.0


def bulge(lng):
    return [ORIGIN, (33.0, lng), DESTINATION]


STRAIGHT = make_route([ORIGIN, DESTINATION], 3 * 3600)  # ~138 mi in 3 h
EAST = make_route(bulge(-96.5), 3.5 * 3600)
WEST = make_route(bulge(-97.5), 3.6 * 3600)


def hours_since_midnight(time_utc):
    return (time_utc - datetime(2026, 11, 3, tzinfo=UTC)).total_seconds() / 3600


def wind_by_hour(lat, lng, time_utc):
    """Wind equals hours since 2026-11-03 00:00 UTC, so each forecast hour is identifiable."""
    return (hours_since_midnight(time_utc), 0.0, 0.0)


def service(routes=(STRAIGHT, EAST, WEST), via=(), weather=None, engine=None, places=None):
    geocoder = FakeGeocoder(places or {"Origin": ORIGIN, "Destination": DESTINATION})
    return AnalysisService(
        geocoder=geocoder,
        router=FakeRoutingProvider(list(routes), via_responses=list(via)),
        weather=weather or FakeWeatherProvider(wind_by_hour),
        engine=engine or RiskEngine(),
        now=lambda: NOW,
    )


def request(interval=25, departure=DEPARTURE, load=LOAD):
    return AnalysisRequest("Origin", "Destination", departure, load, interval)


# --- Checkpoint weather --------------------------------------------------------------


def test_checkpoint_weather_uses_each_eta_not_the_departure():
    result = service().analyze(request())
    straight = next(r for r in result.routes if r.route.geometry == STRAIGHT.geometry)
    forecast_hours = []
    for checkpoint in straight.checkpoints:
        expected_hour = (checkpoint.eta_utc + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        if checkpoint.eta_utc.minute == 30 and checkpoint.eta_utc.second == 0:
            expected_hour -= timedelta(hours=1)  # exact tie goes to the earlier hour
        assert checkpoint.weather.time_utc == expected_hour
        assert checkpoint.weather.wind_mph == hours_since_midnight(expected_hour)
        forecast_hours.append(checkpoint.weather.time_utc)
    assert straight.checkpoints[0].eta_utc == DEPARTURE_UTC
    assert straight.checkpoints[-1].eta_utc == DEPARTURE_UTC + timedelta(hours=3)
    assert len(set(forecast_hours)) > 1


def test_checkpoint_risk_comes_from_matched_weather_and_load():
    def windy_late(lat, lng, time_utc):
        return (47.0 if time_utc >= DEPARTURE_UTC + timedelta(hours=2) else 10.0, 0.0, 0.0)

    result = service(weather=FakeWeatherProvider(windy_late)).analyze(request(load=30_001))
    straight = next(r for r in result.routes if r.route.geometry == STRAIGHT.geometry)
    assert straight.checkpoints[0].assessment.level == 0
    assert straight.checkpoints[-1].assessment.level == 4
    assert straight.checkpoints[-1].assessment.reasons[0].text == "No Travel: wind 47 mph with load over 30,000 lb."


def test_missing_forecast_on_a_final_route_rejects_the_analysis():
    def missing_at_destination(lat, lng, time_utc):
        return None if lat > 33.99 and abs(lng + 97.0) < 0.01 else (5.0, 0.0, 0.0)

    with pytest.raises(ForecastUnavailable) as raised:
        service(weather=FakeWeatherProvider(missing_at_destination)).analyze(request())
    assert raised.value.code == "forecast_unavailable"
    assert "mile" in raised.value.message


def test_incomplete_forecast_hour_is_missing_never_low():
    def no_rain_value(lat, lng, time_utc):
        return (5.0, None, 0.0)

    with pytest.raises(ForecastUnavailable):
        service(weather=FakeWeatherProvider(no_rain_value)).analyze(request())


def test_missing_forecast_on_a_filtered_route_has_no_effect():
    far_east = make_route(bulge(-94.0), 6 * 3600)  # more than 1.5x the fastest: filtered out

    def missing_far_east(lat, lng, time_utc):
        return None if lng > -95.0 else (5.0, 0.0, 0.0)

    weather = FakeWeatherProvider(missing_far_east)
    result = service(routes=(STRAIGHT, EAST, far_east), via=[[WEST]], weather=weather).analyze(request())
    assert far_east.geometry not in [r.route.geometry for r in result.routes]
    assert len(result.routes) == 3
    assert all(lng <= -95.0 for _, lng in weather.requested_locations)


# --- Shared RiskEngine and heatmap -----------------------------------------------------


def test_heatmap_and_checkpoints_use_the_same_risk_engine_and_load():
    engine = SpyRiskEngine()
    result = service(engine=engine).analyze(request(load=12_345))
    checkpoint_count = sum(len(route.checkpoints) for route in result.routes)
    heatmap_cells = sum(1 for point in result.forecast.corridor for value in point.risk if value is not None)
    assert len(engine.calls) == checkpoint_count + heatmap_cells
    assert {call[3] for call in engine.calls} == {12_345}


def test_heatmap_values_equal_the_engine_assessment():
    def stormy(lat, lng, time_utc):
        return (36.0, 0.3, 0.0) if hours_since_midnight(time_utc) >= 20 else (5.0, 0.0, 0.0)

    result = service(weather=FakeWeatherProvider(stormy)).analyze(request(load=40_001))
    point = result.forecast.corridor[0]
    engine = RiskEngine()
    for timestamp, value in zip(result.forecast.timestamps, point.risk):
        hour = timestamp.replace(minute=0)
        expected = engine.assess(*stormy(point.lat, point.lng, hour), 40_001).level
        assert value == int(expected)
    assert 3 in point.risk  # 36 mph with load over 40,000 lb is Severe
    assert 0 in point.risk  # Low stays 0, not None


def test_heatmap_has_49_timestamps_and_aligned_risk_with_null_for_missing_hours():
    cutoff = DEPARTURE_UTC + timedelta(hours=40)

    def data_until_hour_40(lat, lng, time_utc):
        return (5.0, 0.0, 0.0) if time_utc < cutoff else None

    result = service(weather=FakeWeatherProvider(data_until_hour_40)).analyze(request())
    forecast = result.forecast
    assert len(forecast.timestamps) == 49
    assert all(len(point.risk) == 49 for point in forecast.corridor)
    assert all(point.risk[hour] == 0 for point in forecast.corridor for hour in range(40))
    assert all(point.risk[hour] is None for point in forecast.corridor for hour in range(40, 49))
    assert forecast.available_hours == tuple(range(40))
    assert "hours 40-48" in forecast.notice


def test_full_heatmap_has_no_notice():
    forecast = service().analyze(request()).forecast
    assert forecast.available_hours == tuple(range(49))
    assert forecast.notice is None


def test_hour_zero_is_departure_and_hour_n_is_departure_plus_n_hours():
    departure = datetime(2026, 11, 3, 8, 10, tzinfo=timezone(timedelta(hours=5)))
    stamps = service().analyze(request(departure=departure)).forecast.timestamps
    assert stamps[0] == departure.astimezone(UTC)
    assert all(stamps[n] == departure.astimezone(UTC) + timedelta(hours=n) for n in range(49))


def test_slider_hour_matches_forecast_by_the_30_minute_rule():
    departure = datetime(2026, 11, 3, 3, 40, tzinfo=UTC)  # hour N is at :40, so it matches the next hour
    result = service().analyze(request(departure=departure))
    point = result.forecast.corridor[0]
    assert point.risk[0] == 0
    assert result.forecast.available_hours == tuple(range(49))


# --- Trips longer than 48 hours --------------------------------------------------------

LONG_WEST = (35.0, -120.0)
LONG_EAST = (35.0, -75.0)  # about 2,550 miles
LONG_ROUTE = make_route([LONG_WEST, (35.0, -97.5), LONG_EAST], 60 * 3600)


def long_service(weather):
    return service(
        routes=(LONG_ROUTE,), weather=weather, places={"Origin": LONG_WEST, "Destination": LONG_EAST}
    )


def test_trip_longer_than_48_hours_gets_weather_for_every_eta():
    weather = FakeWeatherProvider(wind_by_hour)
    result = long_service(weather).analyze(request(interval=50))
    [route] = result.routes
    last = route.checkpoints[-1]
    assert last.eta_utc == DEPARTURE_UTC + timedelta(hours=60)
    assert last.weather.time_utc == DEPARTURE_UTC + timedelta(hours=60)
    _, start, end = weather.calls[0]
    assert end >= DEPARTURE_UTC + timedelta(hours=60)
    assert start <= DEPARTURE_UTC
    # The slider and corridor still cover hours 0-48 only.
    assert len(result.forecast.timestamps) == 49
    assert result.forecast.timestamps[-1] == DEPARTURE_UTC + timedelta(hours=48)


def test_trip_longer_than_48_hours_without_late_forecasts_is_forecast_unavailable():
    weather = FakeWeatherProvider(wind_by_hour, last_hour=DEPARTURE_UTC + timedelta(hours=48))
    with pytest.raises(ForecastUnavailable):
        long_service(weather).analyze(request(interval=50))


# --- Other outcomes -----------------------------------------------------------------


def test_one_weather_request_with_distinct_locations_within_the_ceiling():
    weather = FakeWeatherProvider()
    result = service(weather=weather).analyze(request(interval=10))
    assert len(weather.calls) == 1
    locations = weather.requested_locations
    assert len(locations) == len(set(locations)) <= MAX_WEATHER_LOCATIONS_PER_ANALYSIS
    assert result.stats.weather_locations == len(locations)


def test_too_many_checkpoints_for_the_budget_rejects_with_validation_error():
    # Three distinct ~1,600-mile routes at a 10-mile interval need more than 450 checkpoints.
    west, east = (35.0, -110.0), (35.0, -82.0)
    routes = [make_route([west, (35.0 + offset, -96.0), east], 30 * 3600 + offset) for offset in (0.0, 3.0, -3.0)]
    svc = service(routes=routes, places={"Origin": west, "Destination": east})
    with pytest.raises(ValidationFailed) as raised:
        svc.analyze(request(interval=10))
    assert "larger sampling interval (25 or 50 miles)" in raised.value.message
    assert svc.weather.calls == []


def test_ranking_labels_ids_and_recommendation():
    result = service().analyze(request())
    assert [r.rank for r in result.routes] == [1, 2, 3]
    assert [r.route_id for r in result.routes] == ["route-1", "route-2", "route-3"]
    assert result.routes[0].label == "Recommended"
    assert result.recommendation.route_id == "route-1"
    # All routes are calm, so travel time decides.
    assert result.recommendation.reason == "Same weather risk as the next route, with the shortest travel time."
    assert result.routes[0].route.geometry == STRAIGHT.geometry


def test_route_notice_is_passed_through_when_fewer_routes_exist():
    result = service(routes=(STRAIGHT,)).analyze(request())
    assert result.route_notice == "Only 1 distinct route was available for this trip."


def test_origin_and_destination_at_the_same_place_are_rejected():
    svc = service(places={"Origin": ORIGIN, "Destination": (32.001, -97.001)})
    with pytest.raises(ValidationFailed) as raised:
        svc.analyze(request())
    assert raised.value.message == "Origin and destination resolve to the same place."


def test_weather_rate_limit_propagates():
    weather = FakeWeatherProvider(error=ProviderRateLimited("wait"))
    with pytest.raises(ProviderRateLimited):
        service(weather=weather).analyze(request())


# --- Stage timings, concurrent geocoding, checkpoint/corridor consistency ----------------


def test_stage_timings_are_recorded():
    stats = service(routes=(STRAIGHT,)).analyze(request()).stats
    assert set(stats.timings) == {"geocoding", "routing", "via", "weather", "risk", "ranking"}
    assert all(value >= 0 for value in stats.timings.values())
    assert stats.timings["via"] > 0  # one route left, so via attempts ran


def test_geocoding_errors_surface_origin_first():
    from core.errors import GeocodingFailed

    # Both places unknown: the origin's error is the one reported, as with sequential calls.
    svc = service(places={"Elsewhere": (40.0, -100.0)})
    with pytest.raises(GeocodingFailed) as raised:
        svc.analyze(request())
    assert '"Origin"' in raised.value.message

    only_destination_unknown = service(places={"Origin": ORIGIN})
    with pytest.raises(GeocodingFailed) as raised:
        only_destination_unknown.analyze(request())
    assert '"Destination"' in raised.value.message


def location_and_hour_weather(lat, lng, time_utc):
    """Varies by place and hour so a mismatch between corridor and checkpoint lookups would show."""
    hour = int(hours_since_midnight(time_utc))
    wind = (abs(lat * 7 + lng * 3) * 5 + hour * 4) % 70
    rain = ((hour * 13 + int(abs(lat) * 10)) % 12) / 10
    return (wind, rain, 0.0)


def test_corridor_and_checkpoint_risk_match_at_the_same_location_and_hour():
    from analysis.geometry import round_location
    from analysis.service import _complete_hours, _match

    weather = FakeWeatherProvider(location_and_hour_weather)
    result = service(weather=weather).analyze(request(interval=25))
    forecasts = dict(zip(weather.calls[0][0], weather.hourly_forecast(weather.calls[0][0], weather.calls[0][1], weather.calls[0][2])))
    corridor = {(point.lat, point.lng): point for point in result.forecast.corridor}

    comparisons = 0
    for route in result.routes:
        for checkpoint in route.checkpoints:
            location = round_location((checkpoint.lat, checkpoint.lng))
            if location not in corridor:
                continue
            table = _complete_hours(forecasts[location].hours)
            for hour, timestamp in enumerate(result.forecast.timestamps):
                matched = _match(timestamp, table)
                if matched is not None and matched.time_utc == checkpoint.weather.time_utc:
                    comparisons += 1
                    assert corridor[location].risk[hour] == int(checkpoint.assessment.level)
    assert comparisons > 10
    assert len({int(c.assessment.level) for r in result.routes for c in r.checkpoints}) > 1


def test_weather_request_carries_a_deadline_inside_the_time_budget():
    import time

    from analysis.limits import ANALYSIS_TIME_BUDGET_SECONDS

    weather = FakeWeatherProvider()
    before = time.monotonic()
    service(weather=weather).analyze(request())
    [deadline] = weather.deadlines
    assert before < deadline <= time.monotonic() + ANALYSIS_TIME_BUDGET_SECONDS
