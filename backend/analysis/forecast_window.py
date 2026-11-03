"""The forecast time range an analysis can use.

Open-Meteo serves hourly forecasts from today 00:00 UTC through the last hour of
day 16 (WEATHER_FORECAST_HORIZON_DAYS); a request ending even one hour later is
rejected with HTTP 400, so every request is clamped to that horizon. Hours past
the horizon simply have no forecast.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .limits import FORECAST_MATCH_WINDOW, FORECAST_SLIDER_HOURS, WEATHER_FORECAST_HORIZON_DAYS
from .time_utils import require_aware


def forecast_horizon_end(now: datetime) -> datetime:
    """The last forecast hour the weather provider serves, in UTC."""
    require_aware(now, "now")
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=WEATHER_FORECAST_HORIZON_DAYS) - timedelta(hours=1)


def _floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(value: datetime) -> datetime:
    floored = _floor_hour(value)
    return floored if floored == value else floored + timedelta(hours=1)


def weather_window(departure_utc: datetime, latest_eta_utc: datetime, horizon_end: datetime) -> tuple[datetime, datetime]:
    """Hours to request so every checkpoint ETA and every slider hour can be matched.

    Covers departure .. max(latest ETA, departure + 48 h), widened by the forecast
    match window on both sides and rounded out to whole hours, then clamped to
    the provider horizon. ETAs beyond 48 hours are therefore still covered.
    """
    for value, name in ((departure_utc, "departure"), (latest_eta_utc, "latest ETA"), (horizon_end, "horizon")):
        require_aware(value, name)
    departure = departure_utc.astimezone(UTC)
    last_needed = max(latest_eta_utc.astimezone(UTC), departure + timedelta(hours=FORECAST_SLIDER_HOURS))
    start = _floor_hour(departure - FORECAST_MATCH_WINDOW)
    end = min(_ceil_hour(last_needed + FORECAST_MATCH_WINDOW), horizon_end.astimezone(UTC))
    return start, max(start, end)


def slider_timestamps(departure_utc: datetime) -> list[datetime]:
    """Hour N of the forecast slider is departure + N hours (N = 0..48)."""
    require_aware(departure_utc, "departure")
    departure = departure_utc.astimezone(UTC)
    return [departure + timedelta(hours=hour) for hour in range(FORECAST_SLIDER_HOURS + 1)]
