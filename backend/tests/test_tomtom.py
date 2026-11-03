import logging
from datetime import UTC, datetime, timedelta, timezone

import pytest
import requests

from core.cache import TTLCache
from core.errors import (
    GeocodingFailed,
    NoRouteFound,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ServiceError,
)
from core.units import METERS_PER_MILE
from routing.tomtom import TomTomGeocodingProvider, TomTomRoutingProvider
from tests.fakes import FakeResponse, FakeSession

API_KEY = "test-secret-key-123"
DEPARTURE = datetime(2026, 11, 3, 8, 0, tzinfo=timezone(timedelta(hours=5)))  # 03:00 UTC
ORIGIN = (32.7780, -96.7962)
DESTINATION = (35.4676, -97.5164)


def geocode_body(lat=32.7779765, lon=-96.7962148, name="Dallas, TX"):
    return {"results": [{"position": {"lat": lat, "lon": lon}, "address": {"freeformAddress": name}}]}


def route_body(length_m=451_813, travel_s=15_243, legs=2, travel_mode="truck"):
    leg_points = [
        [{"latitude": 32.7780, "longitude": -96.7962}, {"latitude": 33.9137, "longitude": -98.4934}],
        [{"latitude": 33.9137, "longitude": -98.4934}, {"latitude": 35.4676, "longitude": -97.5164}],
    ][:legs]
    return {
        "routes": [
            {
                "summary": {"lengthInMeters": length_m, "travelTimeInSeconds": travel_s},
                "legs": [{"points": points} for points in leg_points],
                "progress": [
                    {"pointIndex": 0, "distanceInMeters": 0, "travelTimeInSeconds": 0},
                    {"pointIndex": 1, "distanceInMeters": 227_514, "travelTimeInSeconds": 8_008},
                    {"pointIndex": 3, "distanceInMeters": length_m, "travelTimeInSeconds": travel_s},
                ],
                "sections": [{"sectionType": "TRAVEL_MODE", "travelMode": travel_mode}],
            }
        ]
    }


def routing(replies, cache=None):
    session = FakeSession(replies)
    return TomTomRoutingProvider(API_KEY, session, cache=cache), session


def route(provider, via=()):
    return provider.calculate_routes(ORIGIN, DESTINATION, DEPARTURE, 40_000, 2, via=via)


# --- Geocoding ---------------------------------------------------------------


def test_geocode_parses_first_result_and_sends_key_as_param():
    session = FakeSession([FakeResponse(200, geocode_body())])
    place = TomTomGeocodingProvider(API_KEY, session).geocode("  Dallas,   TX ")
    assert (place.lat, place.lng, place.name, place.query) == (32.7779765, -96.7962148, "Dallas, TX", "Dallas, TX")
    url, params = session.calls[0]
    assert url.endswith("/search/2/geocode/Dallas%2C%20TX.json")
    assert params == {"key": API_KEY, "limit": 1}


def test_geocode_without_results_fails_with_geocoding_failed():
    session = FakeSession([FakeResponse(200, {"results": []})])
    with pytest.raises(GeocodingFailed):
        TomTomGeocodingProvider(API_KEY, session).geocode("Nowhere-ville-zzz")


def test_geocode_blank_query_fails_without_request():
    session = FakeSession([])
    with pytest.raises(GeocodingFailed):
        TomTomGeocodingProvider(API_KEY, session).geocode("   ")
    assert session.calls == []


@pytest.mark.parametrize("body", [{}, {"results": [{"position": {}}]}, {"results": [{"position": {"lat": "x", "lon": 1}}]}])
def test_geocode_malformed_response_is_provider_error(body):
    with pytest.raises(ProviderError):
        TomTomGeocodingProvider(API_KEY, FakeSession([FakeResponse(200, body)])).geocode("Dallas")


def test_geocode_is_cached_case_insensitively():
    session = FakeSession([FakeResponse(200, geocode_body())])
    provider = TomTomGeocodingProvider(API_KEY, session, cache=TTLCache(60))
    first = provider.geocode("Dallas, TX")
    assert provider.geocode("dallas, tx") == first
    assert len(session.calls) == 1


# --- Routing -----------------------------------------------------------------


def test_route_request_parameters():
    provider, session = routing([FakeResponse(200, route_body())])
    route(provider, via=[(33.9137, -98.4934)])
    url, params = session.calls[0]
    assert "/routing/1/calculateRoute/32.778000,-96.796200:33.913700,-98.493400:35.467600,-97.516400/json" in url
    assert params["travelMode"] == "truck"
    assert params["vehicleCommercial"] == "true"
    assert params["vehicleWeight"] == 18_144  # 40,000 lb in kg
    assert params["departAt"] == "2026-11-03T03:00:00Z"
    assert params["maxAlternatives"] == 2
    assert params["routeRepresentation"] == "polyline"
    assert params["extendedRouteRepresentation"] == ["distance", "travelTime"]
    assert params["sectionType"] == "travelMode"
    assert params["key"] == API_KEY


def test_route_is_normalized_on_provider_length():
    provider, _ = routing([FakeResponse(200, route_body())])
    [result] = route(provider, via=[(33.9137, -98.4934)])
    assert result.source == "via"
    assert result.distance_miles == pytest.approx(451_813 / METERS_PER_MILE)
    assert result.cumulative_miles[-1] == result.distance_miles
    assert result.duration_seconds == 15_243
    # Two legs concatenated as returned, including the repeated junction point.
    assert len(result.geometry) == 4
    assert [p.seconds for p in result.progress] == [0, 8_008, 15_243]
    assert result.progress[-1].miles == result.distance_miles


def test_route_without_via_is_marked_provider():
    provider, _ = routing([FakeResponse(200, route_body(legs=1))])
    assert route(provider)[0].source == "provider"


def test_route_rejects_naive_departure():
    provider, session = routing([])
    with pytest.raises(ValueError):
        provider.calculate_routes(ORIGIN, DESTINATION, datetime(2026, 11, 3, 8), 40_000, 2)
    assert session.calls == []


@pytest.mark.parametrize("code", ["NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"])
def test_no_route_engine_errors_map_to_no_route_found(code):
    body = {"detailedError": {"code": code, "message": f"Engine error: {code}"}}
    provider, _ = routing([FakeResponse(400, body)])
    with pytest.raises(NoRouteFound):
        route(provider)


def test_empty_route_list_is_no_route_found():
    provider, _ = routing([FakeResponse(200, {"routes": []})])
    with pytest.raises(NoRouteFound):
        route(provider)


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (FakeResponse(429, {"error": "Too many requests"}), ProviderRateLimited),
        (requests.Timeout("read timed out"), ProviderTimeout),
        (requests.ConnectionError("connection refused"), ProviderError),
        (FakeResponse(500, {"error": "boom"}), ProviderError),
        (FakeResponse(403, {"detailedError": {"code": "FORBIDDEN"}}), ProviderError),
        (FakeResponse(400, {"detailedError": {"code": "BAD_INPUT"}}), ProviderError),
        (FakeResponse(200), ProviderError),  # not JSON
        (FakeResponse(200, {"unexpected": True}), ProviderError),
        (FakeResponse(200, {"routes": [{"summary": {}}]}), ProviderError),
        (FakeResponse(200, {"routes": [{**route_body()["routes"][0], "progress": []}]}), ProviderError),
    ],
)
def test_transport_and_malformed_failures_map_to_stable_errors(reply, error):
    provider, _ = routing([reply])
    with pytest.raises(error) as raised:
        route(provider)
    assert raised.value.code == error.code


def test_api_key_never_appears_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    failures = [
        FakeResponse(500, {"error": API_KEY}),
        FakeResponse(429),
        requests.Timeout(f"timeout for key={API_KEY}"),
        requests.ConnectionError(f"failed key={API_KEY}"),
    ]
    for failure in failures:
        provider, _ = routing([failure])
        with pytest.raises(ServiceError) as raised:
            route(provider)
        assert API_KEY not in str(raised.value)
    assert API_KEY not in caplog.text


def test_non_truck_section_is_logged(caplog):
    caplog.set_level(logging.WARNING)
    provider, _ = routing([FakeResponse(200, route_body(travel_mode="other"))])
    route(provider)
    assert "could not apply truck mode" in caplog.text


def test_route_responses_are_cached():
    provider, session = routing([FakeResponse(200, route_body())], cache=TTLCache(60))
    first = route(provider)
    assert route(provider) == first
    assert len(session.calls) == 1


def test_missing_api_key_is_rejected_at_construction():
    with pytest.raises(ValueError):
        TomTomRoutingProvider("", FakeSession())
    with pytest.raises(ValueError):
        TomTomGeocodingProvider("", FakeSession())


def test_departure_is_sent_in_utc():
    provider, session = routing([FakeResponse(200, route_body())])
    provider.calculate_routes(ORIGIN, DESTINATION, datetime(2026, 11, 3, 3, 0, 30, 999, tzinfo=UTC), 1, 0)
    assert session.calls[0][1]["departAt"] == "2026-11-03T03:00:30Z"


# --- Route cache keys ---------------------------------------------------------------


def cached_router():
    session = FakeSession(responder=lambda url, params: FakeResponse(200, route_body()))
    return TomTomRoutingProvider(API_KEY, session, cache=TTLCache(600)), session


BASE_CALL = {
    "origin": ORIGIN,
    "destination": DESTINATION,
    "departure_utc": datetime(2026, 11, 3, 3, 0, tzinfo=UTC),
    "load_weight_lb": 40_000,
    "max_alternatives": 2,
    "via": (),
}


@pytest.mark.parametrize(
    "change",
    [
        {"origin": (32.7781, -96.7962)},
        {"destination": (35.4677, -97.5164)},
        {"departure_utc": datetime(2026, 11, 3, 4, 0, tzinfo=UTC)},
        {"departure_utc": datetime(2026, 11, 3, 3, 0, 0, 1, tzinfo=UTC)},  # same departAt second, different instant
        {"load_weight_lb": 30_000},
        {"load_weight_lb": 40_000.4},  # rounds to the same whole kg as 40,000 lb
        {"via": ((33.9, -98.5),)},
        {"via": ((33.9, -98.6),)},
        {"max_alternatives": 0},
    ],
)
def test_any_change_to_route_inputs_misses_the_cache(change):
    provider, session = cached_router()
    provider.calculate_routes(**BASE_CALL)
    provider.calculate_routes(**{**BASE_CALL, **change})
    assert len(session.calls) == 2


def test_identical_route_request_hits_the_cache():
    provider, session = cached_router()
    first = provider.calculate_routes(**BASE_CALL)
    same_instant_other_offset = BASE_CALL["departure_utc"].astimezone(timezone(timedelta(hours=5)))
    second = provider.calculate_routes(**{**BASE_CALL, "departure_utc": same_instant_other_offset})
    assert second == first
    assert len(session.calls) == 1


def test_route_travel_modes_are_recorded():
    provider, _ = routing([FakeResponse(200, route_body(travel_mode="truck"))])
    assert route(provider)[0].travel_modes == ("truck",)
