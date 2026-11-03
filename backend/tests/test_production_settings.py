"""Production settings: loaded in a subprocess with a production-like environment."""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PROBE = """
import json
from django.conf import settings
import django
django.setup()
print(json.dumps({
    "DEBUG": settings.DEBUG,
    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    "CORS_ALLOWED_ORIGINS": settings.CORS_ALLOWED_ORIGINS,
    "SECURE_SSL_REDIRECT": settings.SECURE_SSL_REDIRECT,
    "SECURE_PROXY_SSL_HEADER": list(settings.SECURE_PROXY_SSL_HEADER),
    "SECURE_REDIRECT_EXEMPT": settings.SECURE_REDIRECT_EXEMPT,
    "SECURE_HSTS_SECONDS": settings.SECURE_HSTS_SECONDS,
    "INSTALLED_APPS": settings.INSTALLED_APPS,
    "LOG_LEVEL": settings.LOG_LEVEL,
}))
"""


def load_settings(env: dict[str, str]) -> subprocess.CompletedProcess:
    # A clean environment: nothing from the developer's shell or .env leaks in
    # (dotenv never overrides variables that are already set, and these are explicit).
    base = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    full = {**base, "DJANGO_SETTINGS_MODULE": "config.settings", "TOMTOM_API_KEY": "", **env}
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND, env=full, capture_output=True, text=True, timeout=60
    )


PRODUCTION = {
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": "test-production-secret",
    "ALLOWED_HOSTS": "api.example.com",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
}


def test_production_settings_are_locked_down():
    result = load_settings(PRODUCTION)
    assert result.returncode == 0, result.stderr
    settings = json.loads(result.stdout)
    assert settings["DEBUG"] is False
    assert settings["ALLOWED_HOSTS"] == ["api.example.com"]
    assert settings["CORS_ALLOWED_ORIGINS"] == ["https://app.example.com"]
    assert settings["SECURE_SSL_REDIRECT"] is True
    assert settings["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert settings["SECURE_REDIRECT_EXEMPT"] == ["^api/health$"]
    assert settings["SECURE_HSTS_SECONDS"] == 3600
    assert "django.contrib.staticfiles" not in settings["INSTALLED_APPS"]
    assert settings["LOG_LEVEL"] == "INFO"


def test_debug_is_off_by_default_and_never_allows_localhost():
    env = {key: value for key, value in PRODUCTION.items() if key not in ("DJANGO_DEBUG", "ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS")}
    settings = json.loads(load_settings(env).stdout)
    assert settings["DEBUG"] is False
    assert settings["ALLOWED_HOSTS"] == []
    assert settings["CORS_ALLOWED_ORIGINS"] == []


def test_missing_secret_key_fails_in_production():
    result = load_settings({key: value for key, value in PRODUCTION.items() if key != "DJANGO_SECRET_KEY"})
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY must be set" in result.stderr


def test_render_hostname_is_allowed_automatically():
    settings = json.loads(load_settings({**PRODUCTION, "RENDER_EXTERNAL_HOSTNAME": "weather.onrender.com"}).stdout)
    assert settings["ALLOWED_HOSTS"] == ["api.example.com", "weather.onrender.com"]


def test_local_defaults_only_in_debug():
    settings = json.loads(load_settings({"DJANGO_DEBUG": "true"}).stdout)
    assert settings["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1"]
    assert settings["CORS_ALLOWED_ORIGINS"] == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings["SECURE_SSL_REDIRECT"] is False
