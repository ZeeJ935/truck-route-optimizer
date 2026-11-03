"""Choose the final routes to analyse.

1. Request up to MAX_ROUTES truck routes from the routing provider.
2. Remove duplicates, keeping the faster route of each duplicate pair.
3. Remove routes slower than MAX_DURATION_RATIO x the fastest route.
4. While fewer than MAX_ROUTES remain, try via-point alternatives and repeat 2-3.
5. Keep at most the MAX_ROUTES fastest.
Routes are never duplicated or altered to look distinct.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from core.errors import NoRouteFound, ProviderRateLimited, ServiceError
from routing.providers import RoutingProvider
from routing.types import NormalizedRoute

from .geometry import LatLng
from .limits import MAX_DURATION_RATIO, MAX_ROUTES, PROVIDER_MAX_ALTERNATIVES, VIA_OFFSET_FRACTIONS
from .route_similarity import are_duplicates, sample_points

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RouteSelection:
    routes: tuple[NormalizedRoute, ...]
    notice: str | None
    provider_route_count: int
    via_attempts: int
    primary_seconds: float = 0.0
    via_seconds: float = 0.0

    @property
    def used_fallback(self) -> bool:
        return self.via_attempts > 0


def via_points(
    origin: LatLng, destination: LatLng, fractions: Sequence[float] = VIA_OFFSET_FRACTIONS
) -> list[LatLng]:
    """Points offset perpendicular to the straight origin-destination line at its midpoint.

    Uses a local planar approximation (longitude scaled by cos(latitude)).
    """
    mid_lat = (origin[0] + destination[0]) / 2
    mid_lng = (origin[1] + destination[1]) / 2
    cos_lat = max(math.cos(math.radians(mid_lat)), 1e-6)
    dx = (destination[1] - origin[1]) * cos_lat
    dy = destination[0] - origin[0]
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    perp_x, perp_y = -dy / length, dx / length
    return [
        (mid_lat + perp_y * fraction * length, mid_lng + perp_x * fraction * length / cos_lat)
        for fraction in fractions
    ]


def route_notice(count: int) -> str | None:
    if count >= MAX_ROUTES:
        return None
    if count == 1:
        return "Only 1 distinct route was available for this trip."
    return f"Only {count} distinct routes were available for this trip."


class _Selector:
    """Deduplicates and filters candidates, caching each route's samples."""

    def __init__(self) -> None:
        self._samples: dict[int, list[LatLng]] = {}

    def _samples_for(self, route: NormalizedRoute) -> list[LatLng]:
        key = id(route)
        if key not in self._samples:
            self._samples[key] = sample_points(route.geometry, route.cumulative_miles)
        return self._samples[key]

    def dedupe_and_filter(self, candidates: Sequence[NormalizedRoute]) -> list[NormalizedRoute]:
        kept: list[NormalizedRoute] = []
        # Fastest first, so the faster route of each duplicate pair is the one kept.
        # The sort is stable: equal durations keep provider order.
        for route in sorted(candidates, key=lambda r: r.duration_seconds):
            if not any(are_duplicates(self._samples_for(route), self._samples_for(other)) for other in kept):
                kept.append(route)
        if not kept:
            return []
        limit = kept[0].duration_seconds * MAX_DURATION_RATIO
        return [route for route in kept if route.duration_seconds <= limit]


def select_routes(
    routing: RoutingProvider,
    origin: LatLng,
    destination: LatLng,
    departure_utc: datetime,
    load_weight_lb: float,
) -> RouteSelection:
    selector = _Selector()
    started = time.perf_counter()
    candidates = list(
        routing.calculate_routes(origin, destination, departure_utc, load_weight_lb, PROVIDER_MAX_ALTERNATIVES)
    )
    provider_route_count = len(candidates)
    accepted = selector.dedupe_and_filter(candidates)
    primary_seconds = time.perf_counter() - started

    via_started = time.perf_counter()
    attempts = 0
    for via in via_points(origin, destination):
        if len(accepted) >= MAX_ROUTES:
            break
        attempts += 1
        try:
            via_routes = routing.calculate_routes(origin, destination, departure_utc, load_weight_lb, 0, via=(via,))
        except NoRouteFound:
            # The via point could not be routed (e.g. it fell in water); try the next one.
            continue
        except ProviderRateLimited:
            if not accepted:
                raise
            # At least one route is already accepted. Keep it, and stop asking a
            # provider that is rate limiting us.
            logger.warning("Via-point attempt %d was rate limited; keeping %d accepted route(s).", attempts, len(accepted))
            break
        except ServiceError as error:
            if not accepted:
                raise
            # Timeouts and provider errors on an optional via attempt never fail
            # the analysis once a route has been accepted.
            logger.warning(
                "Via-point attempt %d failed (%s); skipping it and keeping %d accepted route(s).",
                attempts,
                error.code,
                len(accepted),
            )
            continue
        candidates.extend(via_routes)
        accepted = selector.dedupe_and_filter(candidates)

    via_seconds = time.perf_counter() - via_started if attempts else 0.0

    final = tuple(sorted(accepted, key=lambda r: r.duration_seconds)[:MAX_ROUTES])
    if not final:
        raise NoRouteFound()
    return RouteSelection(
        routes=final,
        notice=route_notice(len(final)),
        provider_route_count=provider_route_count,
        via_attempts=attempts,
        primary_seconds=primary_seconds,
        via_seconds=via_seconds,
    )
