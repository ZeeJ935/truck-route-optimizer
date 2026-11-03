"""Weather provider interface."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from analysis.geometry import LatLng

from .types import LocationForecast


class WeatherProvider(Protocol):
    def hourly_forecast(
        self, locations: Sequence[LatLng], start_utc: datetime, end_utc: datetime
    ) -> list[LocationForecast]:
        """Hourly forecasts from start_utc to end_utc inclusive, one per location, in input order."""
        ...
