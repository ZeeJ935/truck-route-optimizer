"""Validation of an analysis request. The backend is the authority on every rule."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.errors import ValidationFailed

from .forecast_window import forecast_horizon_end
from .limits import ALLOWED_SAMPLING_INTERVALS_MILES, MAX_PLACE_QUERY_LENGTH, PAST_DEPARTURE_GRACE


@dataclass(frozen=True)
class AnalysisRequest:
    origin: str
    destination: str
    departure: datetime  # as entered, with its UTC offset
    load_weight_lb: float
    sampling_interval_miles: int

    @property
    def departure_utc(self) -> datetime:
        return self.departure.astimezone(UTC)


def _place(payload: Mapping[str, Any], field: str, errors: dict[str, str]) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors[field] = "This field is required."
        return ""
    text = " ".join(value.split())
    if len(text) > MAX_PLACE_QUERY_LENGTH:
        errors[field] = f"Must be at most {MAX_PLACE_QUERY_LENGTH} characters."
    return text


def _departure(payload: Mapping[str, Any], now: datetime, errors: dict[str, str]) -> datetime | None:
    value = payload.get("departure_time")
    if not isinstance(value, str) or not value.strip():
        errors["departure_time"] = "This field is required."
        return None
    try:
        departure = datetime.fromisoformat(value.strip())
    except ValueError:
        errors["departure_time"] = "Use an ISO 8601 date and time with a UTC offset, such as 2026-11-03T08:00:00+05:00."
        return None
    if departure.tzinfo is None or departure.utcoffset() is None:
        errors["departure_time"] = "Include an explicit UTC offset, such as +05:00 or Z."
        return None
    if departure < now - PAST_DEPARTURE_GRACE:
        errors["departure_time"] = "Departure time is in the past."
        return None
    horizon = forecast_horizon_end(now)
    if departure > horizon:
        errors["departure_time"] = (
            f"Departure is beyond the weather forecast range. Choose a time before "
            f"{horizon.strftime('%Y-%m-%d %H:%M')} UTC."
        )
        return None
    return departure


def _load(payload: Mapping[str, Any], errors: dict[str, str]) -> float:
    value = payload.get("load_weight_lb")
    if value is None:
        errors["load_weight_lb"] = "This field is required."
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        errors["load_weight_lb"] = "Load weight must be a number greater than 0."
        return 0.0
    return float(value)


def _interval(payload: Mapping[str, Any], errors: dict[str, str]) -> int:
    value = payload.get("sampling_interval_miles")
    allowed = ", ".join(str(item) for item in ALLOWED_SAMPLING_INTERVALS_MILES)
    if value is None:
        errors["sampling_interval_miles"] = "This field is required."
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value not in ALLOWED_SAMPLING_INTERVALS_MILES:
        errors["sampling_interval_miles"] = f"Sampling interval must be one of {allowed} miles."
        return 0
    return value


def parse_analysis_request(payload: Any, now: Callable[[], datetime]) -> AnalysisRequest:
    if not isinstance(payload, Mapping):
        raise ValidationFailed("The request body must be a JSON object.")
    current = now()
    errors: dict[str, str] = {}
    origin = _place(payload, "origin", errors)
    destination = _place(payload, "destination", errors)
    departure = _departure(payload, current, errors)
    load = _load(payload, errors)
    interval = _interval(payload, errors)
    if errors or departure is None:
        raise ValidationFailed("Please correct the highlighted fields.", fields=errors)
    return AnalysisRequest(
        origin=origin,
        destination=destination,
        departure=departure,
        load_weight_lb=load,
        sampling_interval_miles=interval,
    )
