"""The analysis workflow: geocode, select routes, sample weather, score, rank.

Order of work:
1. Geocode origin and destination.
2. Select the final routes. Filtered routes are never used again.
3. Place checkpoints on each final route and compute their ETAs.
4. Plan the weather location budget and fetch forecasts once, for a window that
   covers every checkpoint ETA (even past 48 hours) and the 0-48 hour slider.
5. Match each checkpoint ETA to an eligible forecast hour; a missing forecast
   rejects the whole analysis.
6. Score checkpoints with the shared RiskEngine, then summarize and rank routes.
7. Build the heatmap with the same RiskEngine and the user's load.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.errors import ForecastUnavailable, ValidationFailed
from risk.engine import RiskAssessment, RiskEngine
from routing.providers import GeocodingProvider, RoutingProvider
from routing.types import GeocodedPlace, NormalizedRoute
from weather.providers import WeatherProvider
from weather.types import HourlyWeather

from .budget import plan_weather_locations
from .checkpoints import place_checkpoints
from .corridor import corridor_points
from .eta import eta_at_mile
from .forecast_matching import match_forecast_hour
from .forecast_window import forecast_horizon_end, slider_timestamps, weather_window
from .geometry import LatLng, haversine_miles, round_location
from .limits import FORECAST_SLIDER_POSITIONS, SAME_PLACE_MAX_MILES
from .request import AnalysisRequest
from .route_selection import select_routes
from .scoring import Recommendation, RiskSegment, RouteRiskSummary, rank_routes, summarize_route

logger = logging.getLogger(__name__)

HourlyTable = Mapping[datetime, HourlyWeather]


@dataclass(frozen=True)
class CheckpointResult:
    mile: float
    lat: float
    lng: float
    eta_utc: datetime
    segment_miles: float
    weather: HourlyWeather
    assessment: RiskAssessment


@dataclass(frozen=True)
class RouteResult:
    route_id: str
    rank: int
    label: str
    route: NormalizedRoute
    summary: RouteRiskSummary
    checkpoints: tuple[CheckpointResult, ...]


@dataclass(frozen=True)
class CorridorPointResult:
    lat: float
    lng: float
    risk: tuple[int | None, ...]


@dataclass(frozen=True)
class ForecastGrid:
    timestamps: tuple[datetime, ...]
    corridor: tuple[CorridorPointResult, ...]
    available_hours: tuple[int, ...]
    notice: str | None


@dataclass(frozen=True)
class AnalysisStats:
    provider_route_count: int
    via_attempts: int
    final_route_count: int
    checkpoint_count: int
    checkpoint_locations: int
    corridor_locations: int
    weather_locations: int
    window_start: datetime
    window_end: datetime
    elapsed_seconds: float
    # Seconds spent per stage: geocoding, routing, via, weather, risk, ranking.
    timings: Mapping[str, float]


@dataclass(frozen=True)
class AnalysisResult:
    origin: GeocodedPlace
    destination: GeocodedPlace
    routes: tuple[RouteResult, ...]  # in rank order
    recommendation: Recommendation
    route_notice: str | None
    forecast: ForecastGrid
    stats: AnalysisStats


def _complete_hours(hours: Sequence[HourlyWeather]) -> dict[datetime, HourlyWeather]:
    """Hours with every value present. Incomplete hours are treated as missing, never as Low."""
    return {hour.time_utc: hour for hour in hours if hour.is_complete}


def _match(target: datetime, table: HourlyTable) -> HourlyWeather | None:
    # Forecast hours are on the hour, so the only hours that can be within the
    # match window are the hour at or before the target and the hour after it.
    floor = target.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    candidates = [hour for hour in (floor, floor + timedelta(hours=1)) if hour in table]
    matched = match_forecast_hour(target, candidates)
    return None if matched is None else table[matched]


def _disabled_hours_notice(available: Sequence[int]) -> str | None:
    missing = [hour for hour in range(FORECAST_SLIDER_POSITIONS) if hour not in set(available)]
    if not missing:
        return None
    if len(missing) == FORECAST_SLIDER_POSITIONS:
        return "No corridor forecast is available for the 48 hours after departure, so the heatmap is empty."
    ranges = []
    start = previous = missing[0]
    for hour in missing[1:]:
        if hour != previous + 1:
            ranges.append((start, previous))
            start = hour
        previous = hour
    ranges.append((start, previous))
    text = ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in ranges)
    noun = "hour" if len(missing) == 1 else "hours"
    return (
        f"No forecast is available for {noun} {text} after departure, so those slider positions "
        f"are disabled. The weather provider forecasts up to 16 days ahead."
    )


class AnalysisService:
    def __init__(
        self,
        geocoder: GeocodingProvider,
        router: RoutingProvider,
        weather: WeatherProvider,
        engine: RiskEngine,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.geocoder = geocoder
        self.router = router
        self.weather = weather
        self.engine = engine
        self.now = now

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = time.perf_counter()
        departure = request.departure_utc
        timings: dict[str, float] = {}

        mark = time.perf_counter()
        origin, destination = self._geocode_both(request.origin, request.destination)
        timings["geocoding"] = time.perf_counter() - mark
        if haversine_miles(origin.position, destination.position) <= SAME_PLACE_MAX_MILES:
            raise ValidationFailed(
                "Origin and destination resolve to the same place.",
                fields={"destination": "Choose a destination different from the origin."},
            )

        selection = select_routes(
            self.router, origin.position, destination.position, departure, request.load_weight_lb
        )
        routes = selection.routes
        timings["routing"] = selection.primary_seconds
        timings["via"] = selection.via_seconds

        placed = []
        for route in routes:
            placements = place_checkpoints(route.geometry, route.cumulative_miles, request.sampling_interval_miles)
            placed.append([(p, eta_at_mile(departure, route.progress, p.mile)) for p in placements])

        budget = plan_weather_locations(
            [(p.lat, p.lng) for route_placements in placed for p, _ in route_placements],
            corridor_points(routes),
            request.sampling_interval_miles,
        )
        latest_eta = max(eta for route_placements in placed for _, eta in route_placements)
        window_start, window_end = weather_window(departure, latest_eta, forecast_horizon_end(self.now()))
        locations = budget.all_locations
        mark = time.perf_counter()
        forecasts = self.weather.hourly_forecast(list(locations), window_start, window_end)
        timings["weather"] = time.perf_counter() - mark
        tables: dict[LatLng, HourlyTable] = {
            location: _complete_hours(forecast.hours) for location, forecast in zip(locations, forecasts)
        }

        mark = time.perf_counter()
        candidates = []
        for index, (route, route_placements) in enumerate(zip(routes, placed)):
            checkpoints = tuple(
                self._score_checkpoint(route, placement, eta, tables, request.load_weight_lb)
                for placement, eta in route_placements
            )
            segments = [RiskSegment(c.segment_miles, c.assessment.level) for c in checkpoints]
            summary = summarize_route(f"candidate-{index}", segments, route.distance_miles, route.duration_seconds)
            candidates.append((summary, route, checkpoints))

        risk_seconds = time.perf_counter() - mark

        mark = time.perf_counter()
        ranking = rank_routes([summary for summary, _, _ in candidates])
        by_candidate = {summary.route_id: (route, checkpoints) for summary, route, checkpoints in candidates}
        final_ids = {ranked.summary.route_id: f"route-{ranked.rank}" for ranked in ranking.routes}
        results = tuple(
            RouteResult(
                route_id=final_ids[ranked.summary.route_id],
                rank=ranked.rank,
                label=ranked.label,
                route=by_candidate[ranked.summary.route_id][0],
                summary=ranked.summary,
                checkpoints=by_candidate[ranked.summary.route_id][1],
            )
            for ranked in ranking.routes
        )
        recommendation = Recommendation(
            route_id=final_ids[ranking.recommendation.route_id],
            reason=ranking.recommendation.reason,
            no_safe_route=ranking.recommendation.no_safe_route,
            deciding_criterion=ranking.recommendation.deciding_criterion,
        )

        timings["ranking"] = time.perf_counter() - mark

        mark = time.perf_counter()
        forecast = self._heatmap(departure, budget.corridor_locations, tables, request.load_weight_lb)
        timings["risk"] = risk_seconds + (time.perf_counter() - mark)

        stats = AnalysisStats(
            provider_route_count=selection.provider_route_count,
            via_attempts=selection.via_attempts,
            final_route_count=len(routes),
            checkpoint_count=sum(len(route_placements) for route_placements in placed),
            checkpoint_locations=len(budget.checkpoint_locations),
            corridor_locations=len(budget.corridor_locations),
            weather_locations=len(locations),
            window_start=window_start,
            window_end=window_end,
            elapsed_seconds=time.perf_counter() - started,
            timings=timings,
        )
        logger.debug("Analysis complete: %s", stats)
        return AnalysisResult(
            origin=origin,
            destination=destination,
            routes=results,
            recommendation=recommendation,
            route_notice=selection.notice,
            forecast=forecast,
            stats=stats,
        )

    def _geocode_both(self, origin_query: str, destination_query: str) -> tuple[GeocodedPlace, GeocodedPlace]:
        """Geocode both places concurrently: the same two requests, in less wall time.

        Errors surface in the same order as sequential calls (origin first).
        """
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="geocode") as pool:
            origin = pool.submit(self.geocoder.geocode, origin_query)
            destination = pool.submit(self.geocoder.geocode, destination_query)
            return origin.result(), destination.result()

    def _score_checkpoint(self, route, placement, eta, tables, load_weight_lb) -> CheckpointResult:
        weather = _match(eta, tables[round_location((placement.lat, placement.lng))])
        if weather is None:
            raise ForecastUnavailable(
                f"No weather forecast is available at mile {placement.mile:.1f} of the "
                f"{route.distance_miles:.0f}-mile route for its arrival time "
                f"({eta.strftime('%Y-%m-%d %H:%M')} UTC). Try an earlier departure."
            )
        assessment = self.engine.assess(
            weather.wind_mph, weather.rain_in_per_hour, weather.snow_in_per_hour, load_weight_lb
        )
        return CheckpointResult(
            mile=placement.mile,
            lat=placement.lat,
            lng=placement.lng,
            eta_utc=eta,
            segment_miles=placement.segment_miles,
            weather=weather,
            assessment=assessment,
        )

    def _heatmap(self, departure, corridor_locations, tables, load_weight_lb) -> ForecastGrid:
        timestamps = tuple(slider_timestamps(departure))
        corridor = []
        for location in corridor_locations:
            table = tables[location]
            risks: list[int | None] = []
            for timestamp in timestamps:
                weather = _match(timestamp, table)
                if weather is None:
                    risks.append(None)
                else:
                    level = self.engine.assess(
                        weather.wind_mph, weather.rain_in_per_hour, weather.snow_in_per_hour, load_weight_lb
                    ).level
                    risks.append(int(level))
            corridor.append(CorridorPointResult(lat=location[0], lng=location[1], risk=tuple(risks)))

        available = tuple(
            hour for hour in range(len(timestamps)) if any(point.risk[hour] is not None for point in corridor)
        )
        return ForecastGrid(
            timestamps=timestamps,
            corridor=tuple(corridor),
            available_hours=available,
            notice=_disabled_hours_notice(available),
        )
