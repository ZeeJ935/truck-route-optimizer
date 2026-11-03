"""TomTom geocoding and truck routing providers.

Responses are normalized before they leave this module. The API key is sent
only as a query parameter and is never logged or included in errors.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from analysis.geometry import LatLng
from analysis.limits import PROVIDER_TIMEOUT_SECONDS
from analysis.time_utils import require_aware
from core.cache import TTLCache
from core.errors import GeocodingFailed, NoRouteFound, ProviderError, ServiceError
from core.http import HttpSession, get_json
from core.units import lb_to_kg, meters_to_miles

from .normalization import normalize_route
from .types import GeocodedPlace, NormalizedRoute

logger = logging.getLogger(__name__)

TOMTOM_BASE_URL = "https://api.tomtom.com"
PROVIDER_NAME = "TomTom"

# TomTom engine error codes (HTTP 400 detailedError.code) that mean no route exists.
# Both were observed live: an unroutable trip and a waypoint that cannot be snapped to a road.
NO_ROUTE_ERROR_CODES = frozenset({"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"})


def _map_routing_error(status: int, body: Any) -> ServiceError | None:
    if status == 400 and isinstance(body, dict):
        detailed = body.get("detailedError")
        code = detailed.get("code") if isinstance(detailed, dict) else None
        if code in NO_ROUTE_ERROR_CODES:
            return NoRouteFound()
    return None


def _format_point(point: LatLng) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def _format_departure(departure_utc: datetime) -> str:
    require_aware(departure_utc, "departure")
    return departure_utc.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProviderError(f"TomTom response is missing {what}.")
    return float(value)


class TomTomGeocodingProvider:
    def __init__(
        self,
        api_key: str,
        session: HttpSession,
        cache: TTLCache | None = None,
        timeout: float = PROVIDER_TIMEOUT_SECONDS,
        base_url: str = TOMTOM_BASE_URL,
    ):
        if not api_key:
            raise ValueError("A TomTom API key is required.")
        self._api_key = api_key
        self._session = session
        self._cache = cache
        self._timeout = timeout
        self._base_url = base_url

    def geocode(self, query: str) -> GeocodedPlace:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise GeocodingFailed("Enter a location.")
        cache_key = ("geocode", normalized_query.lower())
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        url = f"{self._base_url}/search/2/geocode/{quote(normalized_query, safe='')}.json"
        body = get_json(
            self._session,
            url,
            {"key": self._api_key, "limit": 1},
            timeout=self._timeout,
            provider=PROVIDER_NAME,
            secrets=(self._api_key,),
        )
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise ProviderError()
        if not results:
            raise GeocodingFailed(f'"{normalized_query}" could not be found.')

        first = results[0]
        try:
            position = first["position"]
            lat = _number(position["lat"], "a latitude")
            lng = _number(position["lon"], "a longitude")
        except (KeyError, TypeError):
            raise ProviderError() from None
        address = first.get("address") if isinstance(first.get("address"), dict) else {}
        name = address.get("freeformAddress") or normalized_query

        place = GeocodedPlace(query=normalized_query, name=str(name), lat=lat, lng=lng)
        if self._cache is not None:
            self._cache.set(cache_key, place)
        return place


class TomTomRoutingProvider:
    def __init__(
        self,
        api_key: str,
        session: HttpSession,
        cache: TTLCache | None = None,
        timeout: float = PROVIDER_TIMEOUT_SECONDS,
        base_url: str = TOMTOM_BASE_URL,
    ):
        if not api_key:
            raise ValueError("A TomTom API key is required.")
        self._api_key = api_key
        self._session = session
        self._cache = cache
        self._timeout = timeout
        self._base_url = base_url

    def calculate_routes(
        self,
        origin: LatLng,
        destination: LatLng,
        departure_utc: datetime,
        load_weight_lb: float,
        max_alternatives: int,
        via: Sequence[LatLng] = (),
    ) -> list[NormalizedRoute]:
        locations = ":".join(_format_point(point) for point in (origin, *via, destination))
        params = {
            "travelMode": "truck",
            "vehicleCommercial": "true",
            "vehicleWeight": lb_to_kg(load_weight_lb),
            "departAt": _format_departure(departure_utc),
            "maxAlternatives": max_alternatives,
            "routeRepresentation": "polyline",
            "extendedRouteRepresentation": ["distance", "travelTime"],
            "sectionType": "travelMode",
            "traffic": "true",
        }
        cache_key = ("route", locations, tuple(sorted((k, str(v)) for k, v in params.items())))
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return list(cached)

        body = get_json(
            self._session,
            f"{self._base_url}/routing/1/calculateRoute/{locations}/json",
            {**params, "key": self._api_key},
            timeout=self._timeout,
            provider=PROVIDER_NAME,
            secrets=(self._api_key,),
            error_mapper=_map_routing_error,
        )
        raw_routes = body.get("routes") if isinstance(body, dict) else None
        if not isinstance(raw_routes, list):
            raise ProviderError()
        if not raw_routes:
            raise NoRouteFound()

        source = "via" if via else "provider"
        routes = [self._normalize(raw, source) for raw in raw_routes]
        if self._cache is not None:
            self._cache.set(cache_key, tuple(routes))
        return routes

    @staticmethod
    def _normalize(raw: Any, source: str) -> NormalizedRoute:
        try:
            summary = raw["summary"]
            length_m = _number(summary["lengthInMeters"], "a route length")
            travel_s = _number(summary["travelTimeInSeconds"], "a travel time")
            # Leg points are concatenated as returned. TomTom repeats the junction
            # point between legs, and progress pointIndex counts it, so keeping it
            # keeps geometry aligned with the provider's indexing.
            points = [
                (_number(point["latitude"], "a latitude"), _number(point["longitude"], "a longitude"))
                for leg in raw["legs"]
                for point in leg["points"]
            ]
            progress = [
                (
                    meters_to_miles(_number(entry["distanceInMeters"], "progress distance")),
                    _number(entry["travelTimeInSeconds"], "progress travel time"),
                )
                for entry in raw["progress"]
            ]
        except (KeyError, TypeError):
            raise ProviderError() from None

        for section in raw.get("sections") or []:
            if isinstance(section, dict) and section.get("sectionType") == "TRAVEL_MODE":
                if section.get("travelMode") != "truck":
                    logger.warning(
                        "TomTom could not apply truck mode on part of a route (travelMode=%s).",
                        section.get("travelMode"),
                    )

        return normalize_route(points, meters_to_miles(length_m), travel_s, progress, source)
