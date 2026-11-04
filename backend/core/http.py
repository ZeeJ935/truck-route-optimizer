"""HTTP helpers that map transport and provider failures to stable error codes."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from .errors import ProviderError, ProviderRateLimited, ProviderTimeout, ServiceError

logger = logging.getLogger(__name__)

# Optional hook: inspect a non-2xx response and return a more specific error, or None.
ErrorMapper = Callable[[int, Any], ServiceError | None]


class HttpSession(Protocol):
    def get(self, url: str, params: Mapping[str, Any] | None = None, timeout: float | None = None) -> Any: ...


class HttpPostSession(Protocol):
    def post(
        self,
        url: str,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any: ...


def _log_target(url: str) -> str:
    """Only the provider host is logged. URL paths can hold user-entered places
    (for example a geocoding query) and query strings can hold keys."""
    return urlsplit(url).netloc or "provider"


def _json_response(
    send: Callable[[], Any],
    host: str,
    provider: str,
    error_mapper: ErrorMapper | None,
) -> Any:
    try:
        response = send()
    except requests.Timeout:
        logger.warning("%s request timed out: %s", provider, host)
        raise ProviderTimeout() from None
    except requests.RequestException as exc:
        logger.warning("%s request failed: %s (%s)", provider, host, type(exc).__name__)
        raise ProviderError() from None

    status = response.status_code
    if status == 429:
        logger.warning("%s rate limited the request: %s", provider, host)
        raise ProviderRateLimited()

    try:
        body = response.json()
    except ValueError:
        body = None

    if status < 200 or status >= 300:
        if error_mapper is not None:
            mapped = error_mapper(status, body)
            if mapped is not None:
                logger.info("%s returned HTTP %s mapped to %s: %s", provider, status, mapped.code, host)
                raise mapped
        logger.warning("%s returned HTTP %s: %s", provider, status, host)
        raise ProviderError()

    if body is None:
        logger.warning("%s returned a non-JSON body: %s", provider, host)
        raise ProviderError()
    return body


def get_json(
    session: HttpSession,
    url: str,
    params: Mapping[str, Any],
    *,
    timeout: float,
    provider: str,
    error_mapper: ErrorMapper | None = None,
) -> Any:
    return _json_response(
        lambda: session.get(url, params=params, timeout=timeout),
        _log_target(url),
        provider,
        error_mapper,
    )


def post_json(
    session: HttpPostSession,
    url: str,
    body: Any,
    *,
    headers: Mapping[str, str],
    timeout: float,
    provider: str,
    error_mapper: ErrorMapper | None = None,
) -> Any:
    """POST a JSON body. Only the host is logged, so header keys never reach the logs."""
    return _json_response(
        lambda: session.post(url, json=body, headers=headers, timeout=timeout),
        _log_target(url),
        provider,
        error_mapper,
    )
