"""Test doubles. These exist only in test code; production wiring never imports them."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from analysis.geometry import LatLng, cumulative_miles
from core.errors import GeocodingFailed, NoRouteFound
from risk.engine import RiskEngine
from routing.normalization import normalize_route
from routing.types import GeocodedPlace, NormalizedRoute
from weather.types import HourlyWeather, LocationForecast

_NO_JSON = object()


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = _NO_JSON):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if self._payload is _NO_JSON:
            raise ValueError("No JSON body")
        return self._payload


Responder = Callable[[str, dict], FakeResponse]


class FakeSession:
    """Records GET calls and replies from a queue of responses/exceptions, or a responder function."""

    def __init__(self, replies: Sequence[FakeResponse | BaseException] = (), responder: Responder | None = None):
        self._replies = list(replies)
        self._responder = responder
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> FakeResponse:
        params = dict(params or {})
        self.calls.append((url, params))
        if self._responder is not None:
            return self._responder(url, params)
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def make_route(points: Sequence[LatLng], duration_seconds: float, source: str = "provider") -> NormalizedRoute:
    """A normalized route whose provider length equals its geometry length."""
    total = cumulative_miles(points)[-1]
    return normalize_route(points, total, duration_seconds, [(0.0, 0.0), (total, duration_seconds)], source)


class FakeRoutingProvider:
    """Scripted routing: one primary response, then via responses consumed in order."""

    def __init__(
        self,
        primary: Sequence[NormalizedRoute] | BaseException,
        via_responses: Sequence[Sequence[NormalizedRoute] | BaseException] = (),
    ):
        self._primary = primary
        self._via = list(via_responses)
        self.calls: list[dict] = []

    def calculate_routes(self, origin, destination, departure_utc, load_weight_lb, max_alternatives, via=()):
        self.calls.append({"max_alternatives": max_alternatives, "via": tuple(via)})
        response = self._primary if not via else (self._via.pop(0) if self._via else NoRouteFound())
        if isinstance(response, BaseException):
            raise response
        return list(response)


# --- Analysis fakes ------------------------------------------------------------

class FakeGeocoder:
    def __init__(self, places: dict[str, LatLng]):
        self._places = places
        self.calls: list[str] = []

    def geocode(self, query: str) -> GeocodedPlace:
        self.calls.append(query)
        if query not in self._places:
            raise GeocodingFailed(f'"{query}" could not be found.')
        lat, lng = self._places[query]
        return GeocodedPlace(query=query, name=query, lat=lat, lng=lng)


WeatherFn = Callable[[float, float, datetime], tuple[float, float, float] | None]


def calm_weather(lat: float, lng: float, time_utc: datetime) -> tuple[float, float, float]:
    return (5.0, 0.0, 0.0)


class FakeWeatherProvider:
    """Hourly forecasts from a function of (lat, lng, hour). ``None`` from the function means no data.

    ``last_hour`` simulates the provider's forecast horizon: later hours are not returned.
    """

    def __init__(self, values: WeatherFn = calm_weather, last_hour: datetime | None = None, error=None):
        self._values = values
        self._last_hour = last_hour
        self._error = error
        self.calls: list[tuple[list[LatLng], datetime, datetime]] = []

    def hourly_forecast(self, locations, start_utc, end_utc):
        self.calls.append((list(locations), start_utc, end_utc))
        if self._error is not None:
            raise self._error
        end = end_utc if self._last_hour is None else min(end_utc, self._last_hour)
        forecasts = []
        for lat, lng in locations:
            hours = []
            current = start_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
            while current <= end:
                values = self._values(lat, lng, current)
                wind, rain, snow = values if values is not None else (None, None, None)
                hours.append(HourlyWeather(current, wind, rain, snow))
                current += timedelta(hours=1)
            forecasts.append(LocationForecast(lat=lat, lng=lng, hours=tuple(hours)))
        return forecasts

    @property
    def requested_locations(self) -> list[LatLng]:
        return [location for locations, _, _ in self.calls for location in locations]


class SpyRiskEngine(RiskEngine):
    """The real RiskEngine, recording every call."""

    def __init__(self):
        self.calls: list[tuple[float, float, float, float]] = []

    def assess(self, wind_mph, rain_in_per_hour, snow_in_per_hour, load_weight_lb):
        self.calls.append((wind_mph, rain_in_per_hour, snow_in_per_hour, load_weight_lb))
        return super().assess(wind_mph, rain_in_per_hour, snow_in_per_hour, load_weight_lb)
