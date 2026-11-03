"""HTTP helper that maps transport and provider failures to stable error codes."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import requests

from .errors import ProviderError, ProviderRateLimited, ProviderTimeout, ServiceError

logger = logging.getLogger(__name__)

# Optional hook: inspect a non-2xx response and return a more specific error, or None.
ErrorMapper = Callable[[int, Any], ServiceError | None]


class HttpSession(Protocol):
    def get(self, url: str, params: Mapping[str, Any] | None = None, timeout: float | None = None) -> Any: ...


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def get_json(
    session: HttpSession,
    url: str,
    params: Mapping[str, Any],
    *,
    timeout: float,
    provider: str,
    secrets: tuple[str, ...] = (),
    error_mapper: ErrorMapper | None = None,
) -> Any:
    safe_url = _redact(url, secrets)
    try:
        response = session.get(url, params=params, timeout=timeout)
    except requests.Timeout:
        logger.warning("%s request timed out: %s", provider, safe_url)
        raise ProviderTimeout() from None
    except requests.RequestException as exc:
        logger.warning("%s request failed: %s (%s)", provider, safe_url, type(exc).__name__)
        raise ProviderError() from None

    status = response.status_code
    if status == 429:
        logger.warning("%s rate limited the request: %s", provider, safe_url)
        raise ProviderRateLimited()

    try:
        body = response.json()
    except ValueError:
        body = None

    if status < 200 or status >= 300:
        if error_mapper is not None:
            mapped = error_mapper(status, body)
            if mapped is not None:
                logger.info("%s returned HTTP %s mapped to %s: %s", provider, status, mapped.code, safe_url)
                raise mapped
        logger.warning("%s returned HTTP %s: %s", provider, status, safe_url)
        raise ProviderError()

    if body is None:
        logger.warning("%s returned a non-JSON body: %s", provider, safe_url)
        raise ProviderError()
    return body
