"""TomTom place suggestions for the origin and destination fields.

Uses TomTom's Places Search API "Suggest" endpoint, which is built for
as-you-type suggestions (free tier: 10,000 requests per month). The API key is
sent in a request header from the server only; it never reaches the browser.
"""

from __future__ import annotations

import logging
from typing import Any

from analysis.limits import (
    PLACE_SUGGEST_CACHE_TTL_SECONDS,
    PLACE_SUGGEST_COUNTRIES,
    PLACE_SUGGEST_MAX_RESULTS,
    PLACE_SUGGEST_TIMEOUT_SECONDS,
)
from core.cache import TTLCache
from core.errors import ProviderError
from core.http import HttpPostSession, post_json

from .types import PlaceSuggestion

logger = logging.getLogger(__name__)

SUGGEST_URL = "https://api.tomtom.com/maps/orbis/places/suggest"
PROVIDER_NAME = "TomTom Places"
API_VERSION = "3"
# Only the fields this app shows; TomTom requires the Attributes header.
ATTRIBUTES = "results(type,title,subtitles)"
# Result types a driver can route to. POIs and discovery actions are left out.
SUGGEST_TYPES = ["address", "street", "area"]

# Country names TomTom appends as the last subtitle; dropped because the
# suggestion list is already limited to these countries.
COUNTRY_NAMES = {"US": "United States", "CA": "Canada", "MX": "Mexico"}


def suggestion_label(title: str, subtitles: list[str], hidden_countries: set[str]) -> str:
    """'1600 Pennsylvania Avenue' + ['Minneapolis, MN 55426', 'United States'] ->
    '1600 Pennsylvania Avenue, Minneapolis, MN 55426'."""
    parts = [title.strip()]
    for subtitle in subtitles:
        text = subtitle.strip()
        if text and text not in hidden_countries and text not in parts:
            parts.append(text)
    return ", ".join(part for part in parts if part)


def cache_key(query: str) -> str:
    return " ".join(query.lower().split())


class TomTomPlaceSuggestionProvider:
    def __init__(
        self,
        api_key: str,
        session: HttpPostSession,
        cache: TTLCache | None = None,
        timeout: float = PLACE_SUGGEST_TIMEOUT_SECONDS,
        countries: tuple[str, ...] = PLACE_SUGGEST_COUNTRIES,
        max_results: int = PLACE_SUGGEST_MAX_RESULTS,
    ):
        if not api_key:
            raise ValueError("A TomTom API key is required.")
        self._api_key = api_key
        self._session = session
        self._cache = cache
        self._timeout = timeout
        self._countries = countries
        self._max_results = max_results
        self._hidden_countries = {COUNTRY_NAMES[code] for code in countries if code in COUNTRY_NAMES}

    def suggest(self, query: str) -> list[PlaceSuggestion]:
        key = cache_key(query)
        if self._cache is not None:
            cached = self._cache.get(("suggest", key))
            if cached is not None:
                return list(cached)

        filters: dict[str, Any] = {"types": SUGGEST_TYPES}
        if self._countries:
            filters["countryCodesIso2"] = list(self._countries)
        body = post_json(
            self._session,
            SUGGEST_URL,
            {"query": " ".join(query.split()), "maxResults": self._max_results, "filters": filters},
            headers={
                "TomTom-Api-Key": self._api_key,
                "TomTom-Api-Version": API_VERSION,
                "Attributes": ATTRIBUTES,
                "Accept": "application/json",
                "Accept-Language": "en-US",
            },
            timeout=self._timeout,
            provider=PROVIDER_NAME,
        )
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise ProviderError()

        suggestions: list[PlaceSuggestion] = []
        seen: set[str] = set()
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get("title"), str):
                continue
            subtitles = [s for s in result.get("subtitles") or [] if isinstance(s, str)]
            label = suggestion_label(result["title"], subtitles, self._hidden_countries)
            if label and label.lower() not in seen:
                seen.add(label.lower())
                suggestions.append(PlaceSuggestion(label=label, kind=str(result.get("type", "area"))))

        if self._cache is not None:
            self._cache.set(("suggest", key), tuple(suggestions))
        return suggestions
