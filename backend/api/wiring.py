"""Production wiring. Builds the analysis service from real providers only.

There is no flag, setting, parameter, or endpoint that selects another provider.
Test doubles live only in the test suite.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from analysis.limits import GEOCODE_CACHE_TTL_SECONDS, ROUTE_CACHE_TTL_SECONDS, WEATHER_CACHE_TTL_SECONDS
from analysis.service import AnalysisService
from core.cache import TTLCache
from core.errors import ProviderError
from risk.engine import RiskEngine
from routing.tomtom import TomTomGeocodingProvider, TomTomRoutingProvider
from weather.open_meteo import OpenMeteoWeatherProvider

logger = logging.getLogger(__name__)

# Shared for the life of the process, so short-lived caches survive between requests.
_SESSION = requests.Session()
_GEOCODE_CACHE = TTLCache(GEOCODE_CACHE_TTL_SECONDS, max_entries=512)
_ROUTE_CACHE = TTLCache(ROUTE_CACHE_TTL_SECONDS, max_entries=128)
_WEATHER_CACHE = TTLCache(WEATHER_CACHE_TTL_SECONDS, max_entries=20_000)
_RISK_ENGINE = RiskEngine()


def get_analysis_service() -> AnalysisService:
    api_key = settings.TOMTOM_API_KEY
    if not api_key:
        logger.error("TOMTOM_API_KEY is not configured.")
        raise ProviderError("The routing service is not configured.")
    return AnalysisService(
        geocoder=TomTomGeocodingProvider(api_key, _SESSION, cache=_GEOCODE_CACHE),
        router=TomTomRoutingProvider(api_key, _SESSION, cache=_ROUTE_CACHE),
        weather=OpenMeteoWeatherProvider(_SESSION, cache=_WEATHER_CACHE),
        engine=_RISK_ENGINE,
    )
