"""Which client sent a request, for per-client rate limits.

X-Forwarded-For is never trusted: a client can put any value in it, and the
hosting proxy appends to it rather than replacing it. In production the client
address is read only from CLIENT_IP_HEADER, a header that the hosting edge sets
itself and overwrites (configured after verifying it on the host). When that
setting is empty, production has no trustworthy per-client identity, so the
per-client limits are skipped and the global daily weather cap still applies.
Local development uses the socket address.
"""

from __future__ import annotations

import ipaddress

from django.conf import settings


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_identity(request) -> str | None:
    """A trustworthy client address, or None when none is available."""
    header = getattr(settings, "CLIENT_IP_HEADER", "")
    if header:
        return _valid_ip(request.headers.get(header))
    if settings.DEBUG:
        return _valid_ip(request.META.get("REMOTE_ADDR"))
    return None
