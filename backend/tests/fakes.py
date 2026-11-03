"""Test doubles. These exist only in test code; production wiring never imports them."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from analysis.geometry import LatLng, cumulative_miles
from core.errors import NoRouteFound
from routing.normalization import normalize_route
from routing.types import NormalizedRoute

_NO_JSON = object()


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = _NO_JSON):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if self._payload is _NO_JSON:
            raise ValueError("No JSON body")
        return self._payload


Responder = Callable[[str, dict], FakeResponse]


class FakeSession:
    """Records GET calls and replies from a queue of responses/exceptions, or a responder function."""

    def __init__(self, replies: Sequence[FakeResponse | BaseException] = (), responder: Responder | None = None):
        self._replies = list(replies)
        self._responder = responder
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> FakeResponse:
        params = dict(params or {})
        self.calls.append((url, params))
        if self._responder is not None:
            return self._responder(url, params)
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def make_route(points: Sequence[LatLng], duration_seconds: float, source: str = "provider") -> NormalizedRoute:
    """A normalized route whose provider length equals its geometry length."""
    total = cumulative_miles(points)[-1]
    return normalize_route(points, total, duration_seconds, [(0.0, 0.0), (total, duration_seconds)], source)


class FakeRoutingProvider:
    """Scripted routing: one primary response, then via responses consumed in order."""

    def __init__(
        self,
        primary: Sequence[NormalizedRoute] | BaseException,
        via_responses: Sequence[Sequence[NormalizedRoute] | BaseException] = (),
    ):
        self._primary = primary
        self._via = list(via_responses)
        self.calls: list[dict] = []

    def calculate_routes(self, origin, destination, departure_utc, load_weight_lb, max_alternatives, via=()):
        self.calls.append({"max_alternatives": max_alternatives, "via": tuple(via)})
        response = self._primary if not via else (self._via.pop(0) if self._via else NoRouteFound())
        if isinstance(response, BaseException):
            raise response
        return list(response)
