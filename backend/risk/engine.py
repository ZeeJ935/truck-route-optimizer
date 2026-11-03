"""The one shared RiskEngine. Checkpoints and the heatmap both use it.

Order of evaluation:
1. Classify wind, rain, and snow separately.
2. Apply the load rules to the wind result only.
3. The final level is the worst of the three.
4. Keep a reason for every hazard above Low.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from . import thresholds as t
from .levels import RiskLevel


class Hazard(str, Enum):
    WIND = "wind"
    RAIN = "rain"
    SNOW = "snow"


@dataclass(frozen=True)
class RiskReason:
    hazard: Hazard
    level: RiskLevel
    value: float
    load_adjusted: bool
    text: str


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    reasons: tuple[RiskReason, ...]


def _require_measurement(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if number < 0:
        raise ValueError(f"{name} must not be negative, got {value!r}")
    return number


def _format_number(value: float) -> str:
    # %g keeps up to 6 significant digits and never rounds a value across a
    # threshold for the precisions weather providers report (e.g. 54.96 -> "54.96").
    return f"{value:g}"


def _format_pounds(value: float) -> str:
    return f"{value:,.0f}"


def classify_wind(wind_mph: float) -> RiskLevel:
    if wind_mph >= t.WIND_NO_TRAVEL_MIN_MPH:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= t.WIND_SEVERE_MIN_MPH:
        return RiskLevel.SEVERE
    if wind_mph >= t.WIND_HIGH_MIN_MPH:
        return RiskLevel.HIGH
    if wind_mph >= t.WIND_MODERATE_MIN_MPH:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(rain_in_per_hour: float) -> RiskLevel:
    if rain_in_per_hour > t.RAIN_SEVERE_MAX_IN_HR:
        return RiskLevel.NO_TRAVEL
    if rain_in_per_hour >= t.RAIN_SEVERE_MIN_IN_HR:
        return RiskLevel.SEVERE
    if rain_in_per_hour >= t.RAIN_HIGH_MIN_IN_HR:
        return RiskLevel.HIGH
    if rain_in_per_hour >= t.RAIN_MODERATE_MIN_IN_HR:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(snow_in_per_hour: float) -> RiskLevel:
    if snow_in_per_hour > t.SNOW_SEVERE_MAX_IN_HR:
        return RiskLevel.NO_TRAVEL
    if snow_in_per_hour >= t.SNOW_SEVERE_MIN_IN_HR:
        return RiskLevel.SEVERE
    if snow_in_per_hour >= t.SNOW_HIGH_MIN_IN_HR:
        return RiskLevel.HIGH
    if snow_in_per_hour >= t.SNOW_MODERATE_MIN_IN_HR:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def apply_load_rules(wind_level: RiskLevel, load_weight_lb: float) -> tuple[RiskLevel, float | None]:
    """Adjust a wind level for load.

    Returns the adjusted level and, when a load rule changed it, the load limit
    that was exceeded. Wind of 55 mph or more is already No Travel for any load.
    """
    if wind_level == RiskLevel.SEVERE and load_weight_lb > t.SEVERE_WIND_LOAD_LIMIT_LB:
        return RiskLevel.NO_TRAVEL, t.SEVERE_WIND_LOAD_LIMIT_LB
    if wind_level == RiskLevel.HIGH and load_weight_lb > t.HIGH_WIND_LOAD_LIMIT_LB:
        return RiskLevel.SEVERE, t.HIGH_WIND_LOAD_LIMIT_LB
    return wind_level, None


class RiskEngine:
    """Classifies one weather observation for one truck load."""

    def assess(
        self,
        wind_mph: float,
        rain_in_per_hour: float,
        snow_in_per_hour: float,
        load_weight_lb: float,
    ) -> RiskAssessment:
        wind = _require_measurement("wind_mph", wind_mph)
        rain = _require_measurement("rain_in_per_hour", rain_in_per_hour)
        snow = _require_measurement("snow_in_per_hour", snow_in_per_hour)
        load = _require_measurement("load_weight_lb", load_weight_lb)
        if load <= 0:
            raise ValueError(f"load_weight_lb must be greater than 0, got {load_weight_lb!r}")

        reasons: list[RiskReason] = []

        wind_level, exceeded_limit = apply_load_rules(classify_wind(wind), load)
        if wind_level > RiskLevel.LOW:
            text = f"{wind_level.label}: wind {_format_number(wind)} mph"
            if exceeded_limit is not None:
                text += f" with load over {_format_pounds(exceeded_limit)} lb"
            reasons.append(
                RiskReason(Hazard.WIND, wind_level, wind, exceeded_limit is not None, text + ".")
            )

        rain_level = classify_rain(rain)
        if rain_level > RiskLevel.LOW:
            reasons.append(
                RiskReason(
                    Hazard.RAIN,
                    rain_level,
                    rain,
                    False,
                    f"{rain_level.label}: rain {_format_number(rain)} in/hr.",
                )
            )

        snow_level = classify_snow(snow)
        if snow_level > RiskLevel.LOW:
            reasons.append(
                RiskReason(
                    Hazard.SNOW,
                    snow_level,
                    snow,
                    False,
                    f"{snow_level.label}: snow {_format_number(snow)} in/hr.",
                )
            )

        level = max(wind_level, rain_level, snow_level)
        # Worst hazard first so the UI can lead with it; ties keep wind, rain, snow order.
        ordered = tuple(sorted(reasons, key=lambda reason: -reason.level))
        return RiskAssessment(level=level, reasons=ordered)
