"""Normalized routing and geocoding results, independent of any provider."""

from __future__ import annotations

from dataclasses import dataclass

from analysis.eta import ProgressPoint
from analysis.geometry import LatLng


@dataclass(frozen=True)
class GeocodedPlace:
    query: str
    name: str
    lat: float
    lng: float

    @property
    def position(self) -> LatLng:
        return (self.lat, self.lng)


@dataclass(frozen=True)
class NormalizedRoute:
    """A route on one distance basis: the provider's route length.

    ``cumulative_miles`` has one entry per geometry vertex and ends at exactly
    ``distance_miles``; ``progress`` also ends at ``distance_miles`` and
    ``duration_seconds``. Checkpoints, ETAs, and segment miles all use this basis.
    """

    geometry: tuple[LatLng, ...]
    cumulative_miles: tuple[float, ...]
    distance_miles: float
    duration_seconds: float
    progress: tuple[ProgressPoint, ...]
    source: str  # "provider" or "via"
    # Travel mode of each TRAVEL_MODE section the provider reported ("truck", or
    # "other" where truck restrictions could not be applied). Internal only.
    travel_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaceSuggestion:
    """A place to offer while the user types. Only text: the analysis geocodes it later."""

    label: str
    kind: str  # "address", "street", or "area" (cities, regions, postal areas)
