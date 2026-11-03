"""Fake providers must be unreachable from production code."""

import ast
import inspect
from pathlib import Path

import pytest
from django.conf import settings

from api import wiring
from core.errors import ProviderError
from risk.engine import RiskEngine
from routing.tomtom import TomTomGeocodingProvider, TomTomRoutingProvider
from weather.open_meteo import OpenMeteoWeatherProvider

BACKEND = Path(__file__).resolve().parents[1]


def production_modules():
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND)
        if relative.parts[0] in {"tests", ".venv"}:
            continue
        yield relative, path


def test_production_wiring_builds_only_real_providers(settings):
    settings.TOMTOM_API_KEY = "configured-test-key"
    service = wiring.get_analysis_service()
    assert type(service.geocoder) is TomTomGeocodingProvider
    assert type(service.router) is TomTomRoutingProvider
    assert type(service.weather) is OpenMeteoWeatherProvider
    assert type(service.engine) is RiskEngine


def test_wiring_takes_no_parameters_that_could_select_providers():
    assert inspect.signature(wiring.get_analysis_service).parameters == {}


def test_missing_api_key_is_a_provider_error_not_a_fallback(settings):
    settings.TOMTOM_API_KEY = ""
    with pytest.raises(ProviderError):
        wiring.get_analysis_service()


def test_no_production_module_imports_test_code():
    offenders = []
    for relative, path in production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [(str(relative), name) for name in names if name.split(".")[0] in {"tests", "fakes"}]
    assert offenders == []


def test_no_setting_or_environment_switch_for_fakes():
    for relative, path in production_modules():
        text = path.read_text(encoding="utf-8").lower()
        assert "fake" not in text, f"{relative} mentions fakes"
    assert not [name for name in dir(settings) if "FAKE" in name or "PROVIDER" in name]
