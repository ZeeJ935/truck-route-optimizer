"""Normalized hourly weather, independent of any provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HourlyWeather:
    """One forecast hour. A value is None when the provider had no data; it is never 0 by default."""

    time_utc: datetime
    wind_mph: float | None
    rain_in_per_hour: float | None
    snow_in_per_hour: float | None

    @property
    def is_complete(self) -> bool:
        return None not in (self.wind_mph, self.rain_in_per_hour, self.snow_in_per_hour)


@dataclass(frozen=True)
class LocationForecast:
    lat: float
    lng: float
    hours: tuple[HourlyWeather, ...]
