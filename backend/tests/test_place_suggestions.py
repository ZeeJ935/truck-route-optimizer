"""Place suggestions: the TomTom provider (fake HTTP session) and the API endpoint (fake provider)."""

import logging

import pytest
import requests
from django.core.cache import cache
from django.test import Client

from api import wiring
from core.cache import TTLCache
from core.errors import ProviderError, ProviderRateLimited, ProviderTimeout, ServiceError
from routing.place_suggestions import (
    ATTRIBUTES,
    SUGGEST_URL,
    TomTomPlaceSuggestionProvider,
    suggestion_label,
)
from routing.types import PlaceSuggestion
from tests.fakes import FakeResponse, FakeSession

API_KEY = "test-suggest-key-456"

TOMTOM_BODY = {
    "results": [
        {"type": "area", "title": "Dallas, TX", "subtitles": ["United States"]},
        {"type": "address", "title": "1600 Pennsylvania Avenue", "subtitles": ["Minneapolis, MN 55426", "United States"]},
        {"type": "area", "title": "dallas, tx", "subtitles": ["United States"]},  # duplicate label
        {"type": "street", "title": "Main Street", "subtitles": []},
        {"type": "area", "subtitles": ["United States"]},  # malformed: no title
    ]
}


def provider(replies, cache_=None):
    session = FakeSession(replies)
    return TomTomPlaceSuggestionProvider(API_KEY, session, cache=cache_), session


# --- Provider -------------------------------------------------------------------


def test_request_uses_the_existing_key_in_a_header_and_limits_to_routable_us_places():
    tomtom, session = provider([FakeResponse(200, TOMTOM_BODY)])
    tomtom.suggest("  Dall  ")
    [call] = session.posts
    assert call["url"] == SUGGEST_URL
    assert call["headers"]["TomTom-Api-Key"] == API_KEY
    assert call["headers"]["TomTom-Api-Version"] == "3"
    assert call["headers"]["Attributes"] == ATTRIBUTES
    assert call["json"] == {
        "query": "Dall",
        "maxResults": 5,
        "filters": {"types": ["address", "street", "area"], "countryCodesIso2": ["US"]},
    }
    assert API_KEY not in str(call["json"]) and API_KEY not in call["url"]


def test_results_become_readable_labels_without_duplicates_or_malformed_entries():
    tomtom, _ = provider([FakeResponse(200, TOMTOM_BODY)])
    assert tomtom.suggest("Dall") == [
        PlaceSuggestion("Dallas, TX", "area"),
        PlaceSuggestion("1600 Pennsylvania Avenue, Minneapolis, MN 55426", "address"),
        PlaceSuggestion("Main Street", "street"),
    ]


def test_label_drops_only_the_filtered_country():
    assert suggestion_label("Dallas, TX", ["United States"], {"United States"}) == "Dallas, TX"
    assert suggestion_label("Toronto, ON", ["Canada"], {"United States"}) == "Toronto, ON, Canada"


def test_repeat_searches_are_cached_case_and_space_insensitively():
    tomtom, session = provider([FakeResponse(200, TOMTOM_BODY)], cache_=TTLCache(60))
    first = tomtom.suggest("Dall")
    assert tomtom.suggest("  dALL ") == first
    assert len(session.posts) == 1


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (FakeResponse(429, {"detailedError": {"code": "TOO_MANY_REQUESTS"}}), ProviderRateLimited),
        (requests.Timeout(), ProviderTimeout),
        (requests.ConnectionError(), ProviderError),
        (FakeResponse(403, {"detailedError": {"code": "FORBIDDEN"}}), ProviderError),
        (FakeResponse(400, {"detailedError": {"code": "BAD_REQUEST"}}), ProviderError),
        (FakeResponse(200, {"unexpected": True}), ProviderError),
        (FakeResponse(200), ProviderError),
    ],
)
def test_failures_map_to_stable_errors(reply, error):
    tomtom, _ = provider([reply])
    with pytest.raises(error):
        tomtom.suggest("Dall")


def test_key_never_appears_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    for failure in [FakeResponse(500, {"error": API_KEY}), requests.Timeout(f"key={API_KEY}")]:
        tomtom, _ = provider([failure])
        with pytest.raises(ServiceError) as raised:
            tomtom.suggest("Dall")
        assert API_KEY not in str(raised.value)
    assert API_KEY not in caplog.text


def test_missing_key_is_rejected():
    with pytest.raises(ValueError):
        TomTomPlaceSuggestionProvider("", FakeSession())


# --- API endpoint ---------------------------------------------------------------

URL = "/api/places/suggest"


class FakeSuggestions:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else [PlaceSuggestion("Dallas, TX", "area")]
        self.error = error
        self.queries = []

    def suggest(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def use_suggestions(monkeypatch):
    def install(fake):
        monkeypatch.setattr(wiring, "get_place_suggestion_provider", lambda: fake)
        return fake

    return install


def test_endpoint_returns_suggestions(use_suggestions):
    fake = use_suggestions(FakeSuggestions())
    response = Client().get(URL, {"q": "  Dall  "})
    assert response.status_code == 200
    assert response.json() == {"suggestions": [{"label": "Dallas, TX", "type": "area"}]}
    assert fake.queries == ["Dall"]


@pytest.mark.parametrize("query", ["", "Da", "  D  ", "x" * 101])
def test_short_or_long_queries_are_rejected_without_calling_the_provider(use_suggestions, query):
    fake = use_suggestions(FakeSuggestions())
    response = Client().get(URL, {"q": query})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert fake.queries == []


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ProviderRateLimited(), 503, "provider_rate_limited"),
        (ProviderTimeout(), 504, "provider_timeout"),
        (ProviderError(), 502, "provider_error"),
    ],
)
def test_provider_failures_use_the_stable_error_envelope(use_suggestions, error, status, code):
    use_suggestions(FakeSuggestions(error=error))
    response = Client().get(URL, {"q": "Dallas"})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_unexpected_failure_returns_500_without_details(use_suggestions):
    use_suggestions(FakeSuggestions(error=RuntimeError("secret detail")))
    response = Client().get(URL, {"q": "Dallas"})
    assert response.status_code == 500
    assert "secret detail" not in response.content.decode()


def test_requests_per_client_are_rate_limited(use_suggestions, settings):
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    fake = use_suggestions(FakeSuggestions())
    client = Client(HTTP_CF_CONNECTING_IP="198.51.100.20")
    statuses = [client.get(URL, {"q": f"Dallas {i}"}).status_code for i in range(61)]
    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429
    assert len(fake.queries) == 60  # the refused request never reached the provider


def test_wrong_method_is_a_json_405():
    response = Client().post(URL, {"q": "Dallas"})
    assert response.status_code == 405
    assert response.json() == {
        "error": {"code": "method_not_allowed", "message": "This HTTP method is not allowed for this endpoint."}
    }


def test_production_wiring_uses_the_existing_key(settings):
    settings.TOMTOM_API_KEY = "configured-test-key"
    assert type(wiring.get_place_suggestion_provider()) is TomTomPlaceSuggestionProvider
    settings.TOMTOM_API_KEY = ""
    with pytest.raises(ProviderError):
        wiring.get_place_suggestion_provider()
