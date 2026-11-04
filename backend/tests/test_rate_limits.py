"""Per-client rate limits and the global daily weather cap. Fake clocks only: no real sleeps."""

import json

import pytest
from django.core.cache import cache
from django.test import Client
from rest_framework.throttling import SimpleRateThrottle

from analysis.limits import MAX_WEATHER_LOCATIONS_PER_ANALYSIS, WEATHER_DAILY_LOCATION_CAP
from analysis.request import AnalysisRequest
from api import wiring
from core.client_ip import client_identity
from core.errors import DailyLimitReached
from core.quota import DailyQuota
from routing.types import PlaceSuggestion
from tests.fakes import FakeSession
from tests.test_analysis_service import DEPARTURE, service
from tests.test_analyze_api import BODY, fake_service
from weather.open_meteo import OpenMeteoWeatherProvider

ANALYZE = "/api/routes/analyze"
SUGGEST = "/api/places/suggest"


class FakeClock:
    def __init__(self, now=1_800_000_000.0):  # 2027-01-15 08:00 UTC
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(SimpleRateThrottle, "timer", lambda self: fake())
    return fake


@pytest.fixture
def trusted_header(settings):
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    return "HTTP_CF_CONNECTING_IP"


class CountingService:
    """A fake-backed AnalysisService that counts the analyses reaching it."""

    def __init__(self):
        self.inner = fake_service()
        self.now = self.inner.now
        self.calls = 0

    def analyze(self, request):
        self.calls += 1
        return self.inner.analyze(request)


@pytest.fixture
def counting_service(monkeypatch):
    counter = CountingService()
    monkeypatch.setattr(wiring, "get_analysis_service", lambda: counter)
    return counter


def post(client, body=BODY):
    return client.post(ANALYZE, data=json.dumps(body), content_type="application/json")


# --- Analyze: 6 per minute and 60 per day per client --------------------------------


def test_analyze_allows_6_per_minute_then_429_before_any_provider_call(counting_service, trusted_header, clock):
    client = Client(**{trusted_header: "198.51.100.1"})
    statuses = [post(client).status_code for _ in range(7)]
    assert statuses == [200] * 6 + [429]
    assert counting_service.calls == 6  # the refused request never reached the service
    response = post(client)
    error = response.json()["error"]
    assert error["code"] == "rate_limited"
    assert "wait a minute" in error["message"]
    assert int(response["Retry-After"]) >= 1


def test_minute_window_reopens_after_a_minute(counting_service, trusted_header, clock):
    client = Client(**{trusted_header: "198.51.100.2"})
    for _ in range(6):
        post(client)
    assert post(client).status_code == 429
    clock.now += 61
    assert post(client).status_code == 200


def test_analyze_allows_60_per_day(counting_service, trusted_header, clock):
    client = Client(**{trusted_header: "198.51.100.3"})
    statuses = []
    for _ in range(61):
        statuses.append(post(client).status_code)
        clock.now += 11  # under 6 per minute, so only the daily limit applies
    assert statuses == [200] * 60 + [429]
    clock.now += 24 * 3600
    assert post(client).status_code == 200


def test_clients_are_limited_separately(counting_service, trusted_header, clock):
    first = Client(**{trusted_header: "198.51.100.4"})
    second = Client(**{trusted_header: "198.51.100.5"})
    for _ in range(6):
        post(first)
    assert post(first).status_code == 429
    assert post(second).status_code == 200


def test_x_forwarded_for_cannot_dodge_the_limit(counting_service, trusted_header, clock):
    statuses = [
        post(Client(**{trusted_header: "198.51.100.6", "HTTP_X_FORWARDED_FOR": f"203.0.113.{i}"})).status_code
        for i in range(7)
    ]
    assert statuses == [200] * 6 + [429]


def test_the_limit_also_counts_invalid_requests(counting_service, trusted_header, clock):
    client = Client(**{trusted_header: "198.51.100.7"})
    bad = {**BODY, "sampling_interval_miles": 30}
    assert [post(client, bad).status_code for _ in range(7)] == [400] * 6 + [429]


# --- Client identity ------------------------------------------------------------------


class Req:
    def __init__(self, headers=None, remote="10.0.0.1"):
        self.headers = headers or {}
        self.META = {"REMOTE_ADDR": remote}


def test_identity_comes_only_from_the_trusted_header(settings):
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    settings.DEBUG = False
    assert client_identity(Req({"CF-Connecting-IP": "198.51.100.9", "X-Forwarded-For": "192.0.2.1"})) == "198.51.100.9"
    assert client_identity(Req({"X-Forwarded-For": "192.0.2.1"})) is None
    assert client_identity(Req({"CF-Connecting-IP": "not-an-ip"})) is None


def test_production_without_a_trusted_header_has_no_identity(settings):
    settings.CLIENT_IP_HEADER = ""
    settings.DEBUG = False
    assert client_identity(Req({"X-Forwarded-For": "198.51.100.9"}, remote="10.0.0.1")) is None


def test_local_development_uses_the_socket_address(settings):
    settings.CLIENT_IP_HEADER = ""
    settings.DEBUG = True
    assert client_identity(Req({"X-Forwarded-For": "198.51.100.9"}, remote="127.0.0.1")) == "127.0.0.1"


def test_without_a_safe_identity_per_client_limits_are_skipped(counting_service, settings, clock):
    settings.CLIENT_IP_HEADER = ""
    client = Client(HTTP_X_FORWARDED_FOR="198.51.100.8")
    assert [post(client).status_code for _ in range(8)] == [200] * 8


# --- Suggest: 60 per minute per client -----------------------------------------------


def test_suggest_allows_60_per_minute_then_429(monkeypatch, trusted_header, clock):
    calls = []

    class Fake:
        def suggest(self, query):
            calls.append(query)
            return [PlaceSuggestion("Dallas, TX", "area")]

    monkeypatch.setattr(wiring, "get_place_suggestion_provider", lambda: Fake())
    client = Client(**{trusted_header: "198.51.100.10"})
    statuses = [client.get(SUGGEST, {"q": "Dallas"}).status_code for _ in range(61)]
    assert statuses == [200] * 60 + [429]
    assert len(calls) == 60
    assert client.get(SUGGEST, {"q": "Dallas"}).json()["error"]["code"] == "rate_limited"
    clock.now += 61
    assert client.get(SUGGEST, {"q": "Dallas"}).status_code == 200


# --- Global daily weather cap ---------------------------------------------------------


def test_cap_is_8000_uncached_locations():
    assert WEATHER_DAILY_LOCATION_CAP == 8_000


def test_quota_counts_per_utc_day_and_resets_at_midnight():
    clock = FakeClock()
    quota = DailyQuota(1_000, clock=clock)
    quota.consume(600)
    with pytest.raises(DailyLimitReached):
        quota.consume(401)
    assert quota.used == 600
    quota.consume(400)
    with pytest.raises(DailyLimitReached):
        quota.ensure_available(1)
    clock.now += 16 * 3600 + 1  # past midnight UTC
    assert quota.used == 0
    quota.ensure_available(1_000)


def test_analysis_is_refused_before_any_provider_call_if_the_cap_could_be_passed():
    svc = service()
    svc.weather_quota = DailyQuota(WEATHER_DAILY_LOCATION_CAP)
    svc.weather_quota.consume(WEATHER_DAILY_LOCATION_CAP - MAX_WEATHER_LOCATIONS_PER_ANALYSIS + 1)
    with pytest.raises(DailyLimitReached):
        svc.analyze(AnalysisRequest("Origin", "Destination", DEPARTURE, 40000.0, 25))
    assert svc.geocoder.calls == []
    assert svc.router.calls == []
    assert svc.weather.calls == []


def test_analysis_runs_while_the_worst_case_still_fits():
    svc = service()
    svc.weather_quota = DailyQuota(WEATHER_DAILY_LOCATION_CAP)
    svc.weather_quota.consume(WEATHER_DAILY_LOCATION_CAP - MAX_WEATHER_LOCATIONS_PER_ANALYSIS)
    assert svc.analyze(AnalysisRequest("Origin", "Destination", DEPARTURE, 40000.0, 25)).routes


def window_responder(url, params):
    from tests.test_open_meteo import window_responder as respond

    return respond(url, params)


def test_only_uncached_weather_locations_use_the_cap():
    from core.cache import TTLCache
    from tests.test_open_meteo import END, START

    quota = DailyQuota(1_000)
    provider = OpenMeteoWeatherProvider(FakeSession(responder=window_responder), cache=TTLCache(600), quota=quota)
    provider.hourly_forecast([(32.0, -97.0), (33.0, -97.0)], START, END)
    assert quota.used == 2
    provider.hourly_forecast([(32.0, -97.0), (33.0, -97.0), (34.0, -97.0)], START, END)
    assert quota.used == 3  # two cached locations were free; one new location counted


def test_weather_provider_refuses_a_batch_that_would_pass_the_cap():
    from tests.test_open_meteo import END, START

    quota = DailyQuota(1)
    session = FakeSession(responder=window_responder)
    provider = OpenMeteoWeatherProvider(session, quota=quota)
    with pytest.raises(DailyLimitReached):
        provider.hourly_forecast([(32.0, -97.0), (33.0, -97.0)], START, END)
    assert session.calls == []


def test_daily_cap_error_is_a_clear_503(monkeypatch):
    svc = fake_service()
    svc.weather_quota = DailyQuota(100)
    svc.weather_quota.consume(100)
    monkeypatch.setattr(wiring, "get_analysis_service", lambda: svc)
    response = post(Client())
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "daily_limit_reached"
    assert "midnight UTC" in error["message"]


def test_production_wiring_shares_one_quota(settings):
    settings.TOMTOM_API_KEY = "configured-test-key"
    svc = wiring.get_analysis_service()
    assert svc.weather_quota is wiring._WEATHER_QUOTA
    assert svc.weather._quota is wiring._WEATHER_QUOTA
    assert svc.weather_quota.limit == WEATHER_DAILY_LOCATION_CAP
