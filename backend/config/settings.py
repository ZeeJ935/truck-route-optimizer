"""Django settings for the Weather-Aware Truck Routing backend.

The service is stateless: no database, no sessions, no auth, and no static files
(it serves JSON only; the frontend is hosted separately). Every secret and every
deployment-specific value comes from environment variables. In local development
they are loaded from the repo-root .env file.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

# Local development only: a missing file is ignored, and real environment
# variables (as set on the host) always take precedence.
load_dotenv(REPO_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() == "true"


def _env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# Off unless explicitly enabled.
DEBUG = _env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is not true.")
    SECRET_KEY = "local-dev-only-insecure-key"

# Hosts and frontend origins come from the environment. Local defaults apply only
# in debug mode, so production never silently allows localhost.
LOCAL_HOSTS = "localhost,127.0.0.1"
LOCAL_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", LOCAL_HOSTS if DEBUG else "")
# Render sets RENDER_EXTERNAL_HOSTNAME to the service's public host name.
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS", LOCAL_ORIGINS if DEBUG else "")

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Analysis responses are mostly route geometry; gzip shrinks them about 4x.
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

SILENCED_SYSTEM_CHECKS = [
    # CSRF protects cookie-based sessions. This API is stateless JSON with no cookies,
    # sessions, or authentication, so there is no CSRF surface.
    "security.W003",
    # HSTS subdomain and preload flags must not be set: the API runs on a subdomain of
    # the hosting provider's shared domain, which this project does not control.
    "security.W005",
    "security.W021",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES: dict = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# HTTPS. The host's proxy terminates TLS and sets X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", not DEBUG)
# The platform's internal health check calls over plain HTTP; never redirect it.
SECURE_REDIRECT_EXEMPT = [r"^api/health$"]
SECURE_HSTS_SECONDS = 0 if DEBUG else int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "api.errors.drf_exception_handler",
}

# Header that the hosting edge sets (and overwrites) with the real client address,
# used for per-client rate limits. X-Forwarded-For is never trusted. Leave empty
# until the header is verified on the host: production then skips per-client
# limits and relies on the global daily weather cap.
CLIENT_IP_HEADER = os.environ.get("CLIENT_IP_HEADER", "").strip()

# Provider credentials stay server-side only.
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    # Request errors are already logged by the API views with safe messages.
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
