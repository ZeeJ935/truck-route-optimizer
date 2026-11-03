import json
from datetime import UTC, datetime

import pytest
import requests
from django.test import Client

from analysis.service import AnalysisService
from api import wiring
from core.errors import (
    ForecastUnavailable,
    GeocodingFailed,
    NoRouteFound,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
)
from risk.engine import RiskEngine
from tests.fakes import (
    FakeGeocoder,
    FakeResponse,
    FakeRoutingProvider,
    FakeSession,
    FakeWeatherProvider,
    make_route,
)
from weather.open_meteo import OpenMeteoWeatherProvider

URL = "/api/routes/analyze"
NOW = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
ORIGIN = (32.0, -97.0)
DESTINATION = (34.0, -97.0)
STRAIGHT = make_route([ORIGIN, DESTINATION], 3 * 3600)
EAST = make_route([ORIGIN, (33.0, -96.5), DESTINATION], 3.5 * 3600)
WEST = make_route([ORIGIN, (33.0, -97.5), DESTINATION], 3.6 * 3600)

BODY = {
    "origin": "Origin",
    "destination": "Destination",
    "departure_time": "2026-11-03T08:00:00+05:00",
    "load_weight_lb": 40000,
    "sampling_interval_miles": 25,
}


def fake_service(routes=(STRAIGHT, EAST, WEST), via=(), weather=None, geocoder=None):
    return AnalysisService(
        geocoder=geocoder or FakeGeocoder({"Origin": ORIGIN, "Destination": DESTINATION}),
        router=FakeRoutingProvider(list(routes) if not isinstance(routes, BaseException) else routes, list(via)),
        weather=weather or FakeWeatherProvider(),
        engine=RiskEngine(),
        now=lambda: NOW,
    )


@pytest.fixture
def use_service(monkeypatch):
    def install(service):
        monkeypatch.setattr(wiring, "get_analysis_service", lambda: service)
        return service

    return install


def post(body=BODY, raw=None):
    data = raw if raw is not None else json.dumps(body)
    return Client().post(URL, data=data, content_type="application/json")


def test_successful_analysis_has_the_documented_shape(use_service):
    use_service(fake_service())
    response = post()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"routes", "recommendation", "route_notice", "forecast"}

    route = body["routes"][0]
    assert set(route) == {
        "id", "rank", "label", "status", "geometry", "distance_miles", "duration_seconds",
        "no_travel_miles", "severe_miles", "high_miles", "average_risk", "checkpoints",
    }  # fmt: skip
    assert [r["id"] for r in body["routes"]] == ["route-1", "route-2", "route-3"]
    assert route["label"] == "Recommended" and route["status"] == "SAFE"
    assert route["geometry"][0] == [-97.0, 32.0]  # [lng, lat]
    assert route["duration_seconds"] == 10800

    checkpoint = route["checkpoints"][0]
    assert set(checkpoint) == {
        "mile", "lat", "lng", "eta", "segment_miles", "weather", "risk", "risk_label", "reasons",
    }  # fmt: skip
    assert checkpoint["eta"] == "2026-11-03T03:00:00Z"
    assert checkpoint["weather"] == {
        "forecast_time": "2026-11-03T03:00:00Z",
        "wind_mph": 5.0,
        "rain_in_per_hour": 0.0,
        "snow_in_per_hour": 0.0,
    }
    assert (checkpoint["risk"], checkpoint["risk_label"], checkpoint["reasons"]) == (0, "Low", [])

    assert body["recommendation"]["route_id"] == "route-1"
    assert body["recommendation"]["no_safe_route"] is False
    assert body["route_notice"] is None

    forecast = body["forecast"]
    assert len(forecast["timestamps"]) == 49
    assert forecast["timestamps"][0] == "2026-11-03T03:00:00Z"
    assert all(len(point["risk"]) == 49 for point in forecast["corridor"])
    assert forecast["available_hours"] == list(range(49))


def test_validation_error_returns_400_with_fields(use_service):
    use_service(fake_service())
    response = post({**BODY, "departure_time": "2026-11-03T08:00:00", "sampling_interval_miles": 30})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert set(error["fields"]) == {"departure_time", "sampling_interval_miles"}


@pytest.mark.parametrize("raw", ["{not json", "", "[1, 2"])
def test_malformed_json_is_a_validation_error(use_service, raw):
    use_service(fake_service())
    response = post(raw=raw)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_wrong_method_is_rejected():
    assert Client().get(URL).status_code == 405


@pytest.mark.parametrize(
    ("service_kwargs", "status", "code"),
    [
        ({"geocoder": FakeGeocoder({"Origin": ORIGIN})}, 422, "geocoding_failed"),
        ({"routes": NoRouteFound()}, 422, "no_route_found"),
        ({"weather": FakeWeatherProvider(lambda lat, lng, t: None)}, 422, "forecast_unavailable"),
        ({"weather": FakeWeatherProvider(error=ProviderRateLimited())}, 503, "provider_rate_limited"),
        ({"routes": ProviderTimeout()}, 504, "provider_timeout"),
        ({"weather": FakeWeatherProvider(error=ProviderError())}, 502, "provider_error"),
    ],
)
def test_service_errors_map_to_stable_codes_and_statuses(use_service, service_kwargs, status, code):
    use_service(fake_service(**service_kwargs))
    response = post()
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert "Traceback" not in response.content.decode()


def test_open_meteo_429_returns_provider_rate_limited_with_retry_message(use_service):
    session = FakeSession(responder=lambda url, params: FakeResponse(429, {"error": True, "reason": "limit"}))
    sleeps = []
    use_service(fake_service(weather=OpenMeteoWeatherProvider(session, sleep=sleeps.append)))
    response = post()
    assert sleeps == [30]  # one bounded retry, then the error
    assert len(session.calls) == 2
    assert response.status_code == 503
    assert response["Retry-After"] == "60"
    assert response.json()["error"] == {
        "code": "provider_rate_limited",
        "message": "The weather service is receiving too many requests. Please wait about a minute and try again.",
    }


def test_via_timeout_is_skipped_and_the_analysis_succeeds(use_service):
    use_service(fake_service(routes=(STRAIGHT,), via=[ProviderTimeout(), [EAST], [WEST]]))
    response = post()
    assert response.status_code == 200
    assert len(response.json()["routes"]) == 3


def test_unexpected_error_returns_500_without_details(use_service, caplog):
    class Broken(FakeWeatherProvider):
        def hourly_forecast(self, *args, **kwargs):
            raise RuntimeError("secret internal detail")

    use_service(fake_service(weather=Broken()))
    response = post()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.content.decode()
    assert "secret internal detail" in caplog.text  # logged on the server


def test_fewer_routes_notice_is_in_the_response(use_service):
    use_service(fake_service(routes=(STRAIGHT, EAST)))
    assert post().json()["route_notice"] == "Only 2 distinct routes were available for this trip."


def test_global_warning_follows_the_backend_value(use_service):
    use_service(fake_service(weather=FakeWeatherProvider(lambda lat, lng, t: (60.0, 0.0, 0.0))))
    body = post().json()
    assert body["recommendation"]["no_safe_route"] is True
    assert body["routes"][0]["label"] == "Best available, not safe"
    assert all(route["status"] == "NOT_SAFE" for route in body["routes"])


def test_connection_errors_never_leak(use_service):
    session = FakeSession([requests.ConnectionError("dns failure for api.open-meteo.com")])
    use_service(fake_service(weather=OpenMeteoWeatherProvider(session)))
    response = post()
    assert response.status_code == 502
    assert "dns failure" not in response.content.decode()


def test_responses_are_gzipped_when_the_client_accepts_it(use_service):
    use_service(fake_service())
    response = Client().post(URL, data=json.dumps(BODY), content_type="application/json", HTTP_ACCEPT_ENCODING="gzip")
    assert response.status_code == 200
    assert response["Content-Encoding"] == "gzip"


def test_timings_are_logged_without_place_names_or_keys(use_service, caplog, settings):
    import logging

    settings.TOMTOM_API_KEY = "never-log-this-key"
    caplog.set_level(logging.INFO)
    use_service(fake_service())
    assert post().status_code == 200
    lines = [record.getMessage() for record in caplog.records if "analysis timings" in record.getMessage()]
    assert len(lines) == 1
    for stage in ("geocoding=", "routing=", "via=", "weather=", "risk=", "ranking=", "serialization=", "total="):
        assert stage in lines[0]
    assert "Origin" not in lines[0] and "Destination" not in lines[0]
    assert "never-log-this-key" not in caplog.text
