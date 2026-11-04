"""User-entered places never reach application or provider-error logs; error codes still do."""

import logging

import pytest
import requests
from django.test import Client

from api import wiring
from core.errors import GeocodingFailed
from routing.tomtom import TomTomGeocodingProvider
from tests.fakes import FakeGeocoder, FakeResponse, FakeSession
from tests.test_analyze_api import BODY, DESTINATION, fake_service

PLACE = "742 Evergreen Terrace Springfield"


@pytest.mark.parametrize(
    "reply",
    [FakeResponse(500, {}), FakeResponse(429, {}), requests.Timeout(), requests.ConnectionError(), FakeResponse(200)],
)
def test_provider_error_logs_name_the_host_but_not_the_place(caplog, reply):
    caplog.set_level(logging.DEBUG)
    geocoder = TomTomGeocodingProvider("test-key-789", FakeSession([reply]))
    with pytest.raises(Exception):
        geocoder.geocode(PLACE)
    assert "api.tomtom.com" in caplog.text
    assert "Evergreen" not in caplog.text
    assert "test-key-789" not in caplog.text


def test_geocoding_failure_is_logged_as_a_code_without_the_place(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    service = fake_service(geocoder=FakeGeocoder({"Destination": DESTINATION}))
    monkeypatch.setattr(wiring, "get_analysis_service", lambda: service)
    import json

    body = {**BODY, "origin": PLACE}
    response = Client().post("/api/routes/analyze", data=json.dumps(body), content_type="application/json")
    assert response.json()["error"]["code"] == "geocoding_failed"
    assert "geocoding_failed" in caplog.text
    assert "Evergreen" not in caplog.text


def test_no_result_geocoding_logs_nothing_with_the_place(caplog):
    caplog.set_level(logging.DEBUG)
    geocoder = TomTomGeocodingProvider("test-key-789", FakeSession([FakeResponse(200, {"results": []})]))
    with pytest.raises(GeocodingFailed):
        geocoder.geocode(PLACE)
    assert "Evergreen" not in caplog.text


def test_suggest_failures_do_not_log_the_typed_text(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)

    class Failing:
        def suggest(self, query):
            raise requests.ConnectionError(query)

    monkeypatch.setattr(wiring, "get_place_suggestion_provider", lambda: Failing())
    Client().get("/api/places/suggest", {"q": PLACE})
    assert "Evergreen" not in caplog.text
