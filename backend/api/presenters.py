"""Turn an AnalysisResult into the public JSON response.

All values are decided by the analysis; this module only formats them.
Times are UTC ISO 8601 with a Z suffix. Geometry is [lng, lat].
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from analysis.service import AnalysisResult, CheckpointResult, RouteResult

COORDINATE_DECIMALS = 5
MILE_DECIMALS = 1
WEATHER_DECIMALS = 3


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checkpoint(checkpoint: CheckpointResult) -> dict[str, Any]:
    weather = checkpoint.weather
    return {
        "mile": round(checkpoint.mile, MILE_DECIMALS),
        "lat": round(checkpoint.lat, COORDINATE_DECIMALS),
        "lng": round(checkpoint.lng, COORDINATE_DECIMALS),
        "eta": iso_utc(checkpoint.eta_utc),
        "segment_miles": round(checkpoint.segment_miles, MILE_DECIMALS),
        "weather": {
            "forecast_time": iso_utc(weather.time_utc),
            "wind_mph": round(weather.wind_mph, WEATHER_DECIMALS),
            "rain_in_per_hour": round(weather.rain_in_per_hour, WEATHER_DECIMALS),
            "snow_in_per_hour": round(weather.snow_in_per_hour, WEATHER_DECIMALS),
        },
        "risk": int(checkpoint.assessment.level),
        "risk_label": checkpoint.assessment.level.label,
        "reasons": [reason.text for reason in checkpoint.assessment.reasons],
    }


def _route(result: RouteResult) -> dict[str, Any]:
    summary = result.summary
    return {
        "id": result.route_id,
        "rank": result.rank,
        "label": result.label,
        "status": summary.status.value,
        "geometry": [
            [round(lng, COORDINATE_DECIMALS), round(lat, COORDINATE_DECIMALS)] for lat, lng in result.route.geometry
        ],
        "distance_miles": round(summary.distance_miles, MILE_DECIMALS),
        "duration_seconds": round(summary.duration_seconds),
        "no_travel_miles": summary.no_travel_miles,
        "severe_miles": summary.severe_miles,
        "high_miles": summary.high_miles,
        "average_risk": summary.average_risk,
        "checkpoints": [_checkpoint(checkpoint) for checkpoint in result.checkpoints],
    }


def present_analysis(result: AnalysisResult) -> dict[str, Any]:
    forecast = result.forecast
    return {
        "routes": [_route(route) for route in result.routes],
        "recommendation": {
            "route_id": result.recommendation.route_id,
            "reason": result.recommendation.reason,
            "no_safe_route": result.recommendation.no_safe_route,
        },
        "route_notice": result.route_notice,
        "forecast": {
            "timestamps": [iso_utc(timestamp) for timestamp in forecast.timestamps],
            "corridor": [
                {"lat": point.lat, "lng": point.lng, "risk": list(point.risk)} for point in forecast.corridor
            ],
            "available_hours": list(forecast.available_hours),
            "notice": forecast.notice,
        },
    }
