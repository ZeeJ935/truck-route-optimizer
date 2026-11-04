"""Per-client request limits, checked before any TomTom or Open-Meteo call."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

from analysis.limits import ANALYZE_RATE_PER_DAY, ANALYZE_RATE_PER_MINUTE, PLACE_SUGGEST_RATE
from core.client_ip import client_identity
from core.errors import RateLimited


class ClientRateThrottle(SimpleRateThrottle):
    """A rate limit keyed on a trustworthy client address (see core.client_ip)."""

    def get_cache_key(self, request, view):
        ident = client_identity(request)
        if ident is None:
            return None  # no safe identity: skip the per-client limit; global caps still apply
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AnalyzePerMinuteThrottle(ClientRateThrottle):
    scope = "analyze_minute"
    rate = ANALYZE_RATE_PER_MINUTE


class AnalyzePerDayThrottle(ClientRateThrottle):
    scope = "analyze_day"
    rate = ANALYZE_RATE_PER_DAY


class SuggestPerMinuteThrottle(ClientRateThrottle):
    scope = "place_suggest"
    rate = PLACE_SUGGEST_RATE


def enforce(*throttle_classes: type[ClientRateThrottle], request, message: str) -> None:
    """Raise RateLimited if any throttle refuses the request."""
    for throttle_class in throttle_classes:
        throttle = throttle_class()
        if not throttle.allow_request(request, None):
            raise RateLimited(message, retry_after_seconds=int(throttle.wait() or 60))
