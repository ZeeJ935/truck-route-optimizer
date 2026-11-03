"""Provider interfaces. Business logic depends on these, never on a vendor."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from analysis.geometry import LatLng

from .types import GeocodedPlace, NormalizedRoute


class GeocodingProvider(Protocol):
    def geocode(self, query: str) -> GeocodedPlace: ...


class RoutingProvider(Protocol):
    def calculate_routes(
        self,
        origin: LatLng,
        destination: LatLng,
        departure_utc: datetime,
        load_weight_lb: float,
        max_alternatives: int,
        via: Sequence[LatLng] = (),
    ) -> list[NormalizedRoute]: ...
