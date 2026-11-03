"""Route risk mileage, average risk, status, ranking, and recommendation.

Rounding rules:
- Raw segment miles are summed per risk tier, then each total is rounded once
  to 0.1 mile with round-half-up. A nonzero total never rounds below 0.1.
- Average risk is distance-weighted and rounded to 2 decimals with round-half-up.
- The same rounded values drive ranking, status, the global warning, and display.

Ranking is lexicographic (lower is better):
    (no_travel_miles, severe_miles, high_miles, average_risk, travel_time_seconds)
No Travel miles come first: without them, a route with No Travel miles could beat
a route with a small amount of Severe mileage. Travel time only breaks ties.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from risk.levels import RiskLevel

MILES_QUANTUM = Decimal("0.1")
AVERAGE_RISK_QUANTUM = Decimal("0.01")

# Segment miles must add up to the route length within this tolerance.
SEGMENT_SUM_TOLERANCE_MILES = 0.01

LABEL_RECOMMENDED = "Recommended"
LABEL_BEST_AVAILABLE_NOT_SAFE = "Best available, not safe"
LABEL_ALTERNATIVE = "Alternative"


class RouteStatus(str, Enum):
    NOT_SAFE = "NOT_SAFE"
    CAUTION = "CAUTION"
    SAFE = "SAFE"


class RankingCriterion(str, Enum):
    NO_TRAVEL_MILES = "no_travel_miles"
    SEVERE_MILES = "severe_miles"
    HIGH_MILES = "high_miles"
    AVERAGE_RISK = "average_risk"
    TRAVEL_TIME = "travel_time_seconds"


RANKING_ORDER: tuple[RankingCriterion, ...] = tuple(RankingCriterion)

_CRITERION_REASON = {
    RankingCriterion.NO_TRAVEL_MILES: "Fewest No Travel miles among the available routes.",
    RankingCriterion.SEVERE_MILES: "Fewest Severe miles among the available routes.",
    RankingCriterion.HIGH_MILES: "Fewest High miles among the available routes.",
    RankingCriterion.AVERAGE_RISK: "Lowest average risk among the available routes.",
    RankingCriterion.TRAVEL_TIME: "Same weather risk as the next route, with the shortest travel time.",
}
REASON_SINGLE_ROUTE = "Only one route was available."
REASON_FULL_TIE = "Tied with the next route on every ranking value."


def _to_decimal(value: float) -> Decimal:
    # repr gives the shortest decimal string that round-trips, so 0.05 stays 0.05.
    return Decimal(repr(float(value)))


def round_miles(raw_miles: float) -> float:
    """Round to 0.1 mile, half-up. A nonzero value never rounds below 0.1."""
    if not math.isfinite(raw_miles) or raw_miles < 0:
        raise ValueError(f"mileage must be a non-negative finite number, got {raw_miles!r}")
    if raw_miles == 0:
        return 0.0
    rounded = _to_decimal(raw_miles).quantize(MILES_QUANTUM, rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = MILES_QUANTUM
    return float(rounded)


def round_average_risk(raw_average: float) -> float:
    if not math.isfinite(raw_average) or raw_average < 0:
        raise ValueError(f"average risk must be a non-negative finite number, got {raw_average!r}")
    return float(_to_decimal(raw_average).quantize(AVERAGE_RISK_QUANTUM, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class RiskSegment:
    """Raw road miles represented by one checkpoint and that checkpoint's risk."""

    miles: float
    level: RiskLevel


@dataclass(frozen=True)
class RouteRiskSummary:
    route_id: str
    distance_miles: float
    duration_seconds: float
    no_travel_miles: float
    severe_miles: float
    high_miles: float
    moderate_miles: float
    low_miles: float
    average_risk: float
    status: RouteStatus

    def ranking_key(self) -> tuple[float, ...]:
        return tuple(self.ranking_value(criterion) for criterion in RANKING_ORDER)

    def ranking_value(self, criterion: RankingCriterion) -> float:
        if criterion is RankingCriterion.TRAVEL_TIME:
            return self.duration_seconds
        return getattr(self, criterion.value)


def route_status(no_travel_miles: float, severe_miles: float) -> RouteStatus:
    """Status from rounded mileage. High miles alone never make a route unsafe."""
    if no_travel_miles > 0:
        return RouteStatus.NOT_SAFE
    if severe_miles > 0:
        return RouteStatus.CAUTION
    return RouteStatus.SAFE


def summarize_route(
    route_id: str,
    segments: Sequence[RiskSegment],
    total_miles: float,
    duration_seconds: float,
) -> RouteRiskSummary:
    if not segments:
        raise ValueError("A route needs at least one risk segment.")
    if not math.isfinite(total_miles) or total_miles <= 0:
        raise ValueError(f"route length must be positive, got {total_miles!r}")
    if not math.isfinite(duration_seconds) or duration_seconds < 0:
        raise ValueError(f"duration must be non-negative, got {duration_seconds!r}")

    raw_by_level = {level: 0.0 for level in RiskLevel}
    weighted = 0.0
    for segment in segments:
        if not math.isfinite(segment.miles) or segment.miles < 0:
            raise ValueError(f"segment miles must be non-negative, got {segment.miles!r}")
        raw_by_level[segment.level] += segment.miles
        weighted += segment.miles * int(segment.level)

    covered = sum(raw_by_level.values())
    if abs(covered - total_miles) > SEGMENT_SUM_TOLERANCE_MILES:
        raise ValueError(f"segment miles ({covered}) do not add up to the route length ({total_miles}).")

    no_travel = round_miles(raw_by_level[RiskLevel.NO_TRAVEL])
    severe = round_miles(raw_by_level[RiskLevel.SEVERE])
    return RouteRiskSummary(
        route_id=route_id,
        distance_miles=total_miles,
        duration_seconds=duration_seconds,
        no_travel_miles=no_travel,
        severe_miles=severe,
        high_miles=round_miles(raw_by_level[RiskLevel.HIGH]),
        moderate_miles=round_miles(raw_by_level[RiskLevel.MODERATE]),
        low_miles=round_miles(raw_by_level[RiskLevel.LOW]),
        average_risk=round_average_risk(weighted / total_miles),
        status=route_status(no_travel, severe),
    )


@dataclass(frozen=True)
class RankedRoute:
    summary: RouteRiskSummary
    rank: int
    label: str


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    reason: str
    no_safe_route: bool
    deciding_criterion: RankingCriterion | None


@dataclass(frozen=True)
class RankingResult:
    routes: tuple[RankedRoute, ...]
    recommendation: Recommendation


def deciding_criterion(winner: RouteRiskSummary, runner_up: RouteRiskSummary) -> RankingCriterion | None:
    """The first ranking value that separates two routes, or None on a full tie."""
    for criterion in RANKING_ORDER:
        if winner.ranking_value(criterion) != runner_up.ranking_value(criterion):
            return criterion
    return None


def rank_routes(summaries: Sequence[RouteRiskSummary]) -> RankingResult:
    if not summaries:
        raise ValueError("At least one route is required to rank.")

    # sorted() is stable, so fully tied routes keep their input order.
    ordered = sorted(summaries, key=lambda summary: summary.ranking_key())
    no_safe_route = all(summary.no_travel_miles > 0 for summary in ordered)
    top_label = LABEL_BEST_AVAILABLE_NOT_SAFE if no_safe_route else LABEL_RECOMMENDED

    ranked = tuple(
        RankedRoute(summary=summary, rank=index + 1, label=top_label if index == 0 else LABEL_ALTERNATIVE)
        for index, summary in enumerate(ordered)
    )

    criterion: RankingCriterion | None = None
    if len(ordered) == 1:
        reason = REASON_SINGLE_ROUTE
    else:
        criterion = deciding_criterion(ordered[0], ordered[1])
        reason = REASON_FULL_TIE if criterion is None else _CRITERION_REASON[criterion]

    return RankingResult(
        routes=ranked,
        recommendation=Recommendation(
            route_id=ordered[0].route_id,
            reason=reason,
            no_safe_route=no_safe_route,
            deciding_criterion=criterion,
        ),
    )
