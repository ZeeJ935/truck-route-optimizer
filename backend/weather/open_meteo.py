"""Open-Meteo hourly forecast provider.

Mapping (units requested explicitly, timestamps in GMT):
- wind_mph          = wind_speed_10m (sustained 10 m wind, not gusts), mph
- rain_in_per_hour  = rain + showers, inches over the preceding hour
- snow_in_per_hour  = snowfall, inches over the preceding hour
Open-Meteo precipitation is a sum over the preceding hour; it is used as the
hourly rate. A null value stays None and is never treated as 0.

Coordinates are rounded and deduplicated, so each distinct location is
requested once. Each location counts as one call against Open-Meteo's limits.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from analysis.geometry import LatLng, round_location
from analysis.limits import (
    PROVIDER_TIMEOUT_SECONDS,
    WEATHER_BATCH_SIZE,
    WEATHER_COORD_DECIMALS,
    WEATHER_RETRY_DELAY_SECONDS,
    WEATHER_RETRY_MARGIN_SECONDS,
)
from analysis.time_utils import require_aware
from core.cache import TTLCache
from core.errors import ProviderError, ProviderRateLimited
from core.http import HttpSession, get_json

from .types import HourlyWeather, LocationForecast

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER_NAME = "Open-Meteo"
RATE_LIMIT_MESSAGE = (
    "The weather service is receiving too many requests. Please wait about a minute and try again."
)

HOURLY_VARIABLES = ("wind_speed_10m", "rain", "showers", "snowfall")
PRECIPITATION_SUM_DECIMALS = 6
EXPECTED_UNITS = {"wind_speed_10m": "mp/h", "rain": "inch", "showers": "inch", "snowfall": "inch"}


def _floor_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(value: datetime) -> datetime:
    floored = _floor_hour(value)
    return floored if floored == value.astimezone(UTC) else floored + timedelta(hours=1)


def _format_hour(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProviderError("Open-Meteo returned an invalid weather value.")
    return float(value)


def _sum_precipitation(first: float, second: float) -> float:
    # Provider values have at most a few decimals; rounding removes binary float
    # noise (0.07 + 0.03 = 0.09999999999999999) that could cross a risk threshold.
    return round(first + second, PRECIPITATION_SUM_DECIMALS)


def _parse_location(raw: Any) -> tuple[HourlyWeather, ...]:
    if not isinstance(raw, dict):
        raise ProviderError()
    units = raw.get("hourly_units")
    hourly = raw.get("hourly")
    if not isinstance(units, dict) or not isinstance(hourly, dict):
        raise ProviderError()
    for variable, unit in EXPECTED_UNITS.items():
        if units.get(variable) != unit:
            raise ProviderError("Open-Meteo returned unexpected units.")
    if raw.get("utc_offset_seconds") != 0:
        raise ProviderError("Open-Meteo returned non-UTC timestamps.")

    times = hourly.get("time")
    columns = {variable: hourly.get(variable) for variable in HOURLY_VARIABLES}
    if not isinstance(times, list) or any(
        not isinstance(column, list) or len(column) != len(times) for column in columns.values()
    ):
        raise ProviderError()

    hours = []
    for index, stamp in enumerate(times):
        try:
            time_utc = datetime.strptime(stamp, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            raise ProviderError() from None
        rain = _optional_number(columns["rain"][index])
        showers = _optional_number(columns["showers"][index])
        hours.append(
            HourlyWeather(
                time_utc=time_utc,
                wind_mph=_optional_number(columns["wind_speed_10m"][index]),
                rain_in_per_hour=None if rain is None or showers is None else _sum_precipitation(rain, showers),
                snow_in_per_hour=_optional_number(columns["snowfall"][index]),
            )
        )
    return tuple(hours)


class OpenMeteoWeatherProvider:
    def __init__(
        self,
        session: HttpSession,
        cache: TTLCache | None = None,
        timeout: float = PROVIDER_TIMEOUT_SECONDS,
        url: str = OPEN_METEO_FORECAST_URL,
        batch_size: int = WEATHER_BATCH_SIZE,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        self._session = session
        self._cache = cache
        self._timeout = timeout
        self._url = url
        self._batch_size = batch_size
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic

    def hourly_forecast(
        self,
        locations: Sequence[LatLng],
        start_utc: datetime,
        end_utc: datetime,
        deadline: float | None = None,
    ) -> list[LocationForecast]:
        """Forecasts for each location, in input order.

        ``deadline`` is a ``clock()`` value the call must finish by. On a 429 the
        provider waits WEATHER_RETRY_DELAY_SECONDS and retries the unfinished
        batches once, but only if that still fits before the deadline.
        """
        require_aware(start_utc, "start_utc")
        require_aware(end_utc, "end_utc")
        start = _floor_hour(start_utc)
        end = _ceil_hour(end_utc)
        if end < start:
            raise ValueError("end_utc must not be before start_utc.")
        window = (_format_hour(start), _format_hour(end))

        rounded = [round_location(point) for point in locations]
        unique = list(dict.fromkeys(rounded))

        results: dict[LatLng, tuple[HourlyWeather, ...]] = {}
        missing = []
        for point in unique:
            cached = self._cache.get(("weather", point, window)) if self._cache is not None else None
            if cached is None:
                missing.append(point)
            else:
                results[point] = cached

        batches = [missing[offset : offset + self._batch_size] for offset in range(0, len(missing), self._batch_size)]
        pending = self._fetch_batches(batches, window, results)
        if pending:
            retry_finishes_at = self._clock() + WEATHER_RETRY_DELAY_SECONDS + WEATHER_RETRY_MARGIN_SECONDS
            if deadline is not None and retry_finishes_at > deadline:
                logger.warning("Open-Meteo rate limited the request; no time left to retry %d batch(es).", len(pending))
                raise ProviderRateLimited(RATE_LIMIT_MESSAGE)
            logger.warning(
                "Open-Meteo rate limited the request; retrying %d of %d batch(es) once in %d s.",
                len(pending),
                len(batches),
                WEATHER_RETRY_DELAY_SECONDS,
            )
            self._sleep(WEATHER_RETRY_DELAY_SECONDS)
            if self._fetch_batches(pending, window, results):
                logger.warning("Open-Meteo rate limited the retry as well.")
                raise ProviderRateLimited(RATE_LIMIT_MESSAGE)

        return [LocationForecast(lat=point[0], lng=point[1], hours=results[point]) for point in rounded]

    def _fetch_batches(
        self,
        batches: Sequence[Sequence[LatLng]],
        window: tuple[str, str],
        results: dict[LatLng, tuple[HourlyWeather, ...]],
    ) -> list[Sequence[LatLng]]:
        """Fetch batches in order, storing results. Returns the batches left unfinished by a 429.

        After a 429 no further batches are sent, because the per-minute limit is
        already hit. Completed batches stay in ``results`` and are never requested again.
        """
        for index, batch in enumerate(batches):
            try:
                hours_by_point = self._fetch(batch, window)
            except ProviderRateLimited:
                return list(batches[index:])
            for point, hours in zip(batch, hours_by_point):
                results[point] = hours
                if self._cache is not None:
                    self._cache.set(("weather", point, window), hours)
        return []

    def _fetch(self, batch: Sequence[LatLng], window: tuple[str, str]) -> list[tuple[HourlyWeather, ...]]:
        params = {
            "latitude": ",".join(f"{lat:.{WEATHER_COORD_DECIMALS}f}" for lat, _ in batch),
            "longitude": ",".join(f"{lng:.{WEATHER_COORD_DECIMALS}f}" for _, lng in batch),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "timeformat": "iso8601",
            "start_hour": window[0],
            "end_hour": window[1],
        }
        try:
            body = get_json(self._session, self._url, params, timeout=self._timeout, provider=PROVIDER_NAME)
        except ProviderRateLimited:
            raise ProviderRateLimited(RATE_LIMIT_MESSAGE) from None
        # One location returns an object; several return a list in request order.
        items = [body] if isinstance(body, dict) else body
        if not isinstance(items, list) or len(items) != len(batch):
            raise ProviderError()
        return [_parse_location(item) for item in items]
