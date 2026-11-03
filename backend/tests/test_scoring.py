import pytest

from analysis.scoring import (
    LABEL_ALTERNATIVE,
    LABEL_BEST_AVAILABLE_NOT_SAFE,
    LABEL_RECOMMENDED,
    REASON_FULL_TIE,
    REASON_SINGLE_ROUTE,
    RankingCriterion,
    RiskSegment,
    RouteRiskSummary,
    RouteStatus,
    rank_routes,
    round_average_risk,
    round_miles,
    route_status,
    summarize_route,
)
from risk.levels import RiskLevel

L, M, H, S, N = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


def summary(route_id, no_travel=0.0, severe=0.0, high=0.0, average=0.0, duration=3_600.0):
    return RouteRiskSummary(
        route_id=route_id,
        distance_miles=100.0,
        duration_seconds=duration,
        no_travel_miles=no_travel,
        severe_miles=severe,
        high_miles=high,
        moderate_miles=0.0,
        low_miles=0.0,
        average_risk=average,
        status=route_status(no_travel, severe),
    )


def route(route_id, segments, duration=3_600.0):
    risk_segments = [RiskSegment(miles, level) for miles, level in segments]
    return summarize_route(route_id, risk_segments, sum(miles for miles, _ in segments), duration)


# --- Rounding ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "rounded"),
    [
        (0, 0.0),
        (0.03, 0.1),
        (0.0001, 0.1),
        (0.05, 0.1),
        (0.149, 0.1),
        (0.15, 0.2),
        (0.25, 0.3),
        (2.45, 2.5),
        (12.34, 12.3),
        (12.35, 12.4),
        (99.95, 100.0),
    ],
)
def test_round_miles_half_up_with_nonzero_floor(raw, rounded):
    assert round_miles(raw) == rounded


@pytest.mark.parametrize(("raw", "rounded"), [(0.745, 0.75), (0.744, 0.74), (1.005, 1.01), (0, 0.0), (4, 4.0)])
def test_round_average_risk_half_up(raw, rounded):
    assert round_average_risk(raw) == rounded


def test_round_miles_rejects_negative():
    with pytest.raises(ValueError):
        round_miles(-0.1)


# --- Mileage and average risk ------------------------------------------------


def test_tier_totals_sum_raw_miles_then_round_once():
    # Three 0.04-mile Severe segments: 0.12 raw -> 0.1, not 3 x 0.1 = 0.3.
    result = route("r", [(0.04, S), (0.04, S), (0.04, S), (99.88, L)])
    assert result.severe_miles == 0.1
    assert result.low_miles == 99.9


def test_average_risk_is_distance_weighted():
    # 100 Low + 10 Severe vs 10 Low + 100 Severe.
    mostly_low = route("a", [(100, L), (10, S)])
    mostly_severe = route("b", [(10, L), (100, S)])
    assert mostly_low.average_risk == round_average_risk(30 / 110)  # 0.27
    assert mostly_severe.average_risk == round_average_risk(300 / 110)  # 2.73
    assert mostly_low.average_risk != mostly_severe.average_risk


def test_average_risk_is_not_a_checkpoint_average():
    # Two checkpoints: a short No Travel stretch and a long Low stretch.
    # Checkpoint average would be 2.0; distance-weighted is 4 * 1 / 101.
    result = route("r", [(1, N), (100, L)])
    assert result.average_risk == 0.04


def test_segments_must_cover_route_length():
    with pytest.raises(ValueError):
        summarize_route("r", [RiskSegment(50, L)], total_miles=60, duration_seconds=10)


# --- Status ------------------------------------------------------------------


def test_status_not_safe_caution_safe():
    assert route("a", [(1, N), (99, L)]).status == RouteStatus.NOT_SAFE
    assert route("b", [(1, S), (99, L)]).status == RouteStatus.CAUTION
    assert route("c", [(100, L)]).status == RouteStatus.SAFE


def test_high_miles_alone_stay_safe_but_are_reported():
    result = route("r", [(60, H), (40, L)])
    assert result.status == RouteStatus.SAFE
    assert result.high_miles == 60.0


def test_tiny_no_travel_mileage_rounds_up_and_makes_route_not_safe():
    tiny = route("tiny", [(0.03, N), (99.97, L)], duration=1_000)
    clean = route("clean", [(100, S)], duration=9_000)
    assert tiny.no_travel_miles == 0.1
    assert tiny.status == RouteStatus.NOT_SAFE
    result = rank_routes([tiny, clean])
    assert [r.summary.route_id for r in result.routes] == ["clean", "tiny"]


# --- Ranking -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("better", "worse", "criterion"),
    [
        (summary("w", no_travel=0.0), summary("l", no_travel=0.1), RankingCriterion.NO_TRAVEL_MILES),
        (summary("w", severe=1.0), summary("l", severe=1.1), RankingCriterion.SEVERE_MILES),
        (summary("w", high=5.0), summary("l", high=5.1), RankingCriterion.HIGH_MILES),
        (summary("w", average=0.74), summary("l", average=0.75), RankingCriterion.AVERAGE_RISK),
        (summary("w", duration=3_599), summary("l", duration=3_600), RankingCriterion.TRAVEL_TIME),
    ],
)
def test_each_ranking_value_decides_when_earlier_values_tie(better, worse, criterion):
    for order in ([better, worse], [worse, better]):
        result = rank_routes(order)
        assert result.routes[0].summary.route_id == "w"
        assert result.recommendation.route_id == "w"
        assert result.recommendation.deciding_criterion == criterion


def test_earlier_value_beats_all_later_values():
    # Fewer No Travel miles beat fewer Severe, High, average risk, and travel time.
    a = summary("a", no_travel=0.1, severe=0.0, high=0.0, average=0.1, duration=1_000)
    b = summary("b", no_travel=0.0, severe=50.0, high=80.0, average=2.5, duration=9_000)
    assert rank_routes([a, b]).routes[0].summary.route_id == "b"

    # Fewer Severe miles beat fewer High miles.
    c = summary("c", severe=0.2, high=0.0)
    d = summary("d", severe=0.1, high=90.0)
    assert rank_routes([c, d]).routes[0].summary.route_id == "d"


def test_ranking_uses_rounded_values_not_raw_miles():
    # Raw Severe miles 8.01 and 8.04 both round to 8.0, so they tie and High miles decide.
    # Ranking on raw values would pick the 8.01 route; ranking on rounded values picks
    # the 8.04 route because it has fewer High miles.
    raw_lower_severe = route("raw-8.01", [(8.01, S), (20, H), (71.99, L)])
    raw_higher_severe = route("raw-8.04", [(8.04, S), (10, H), (81.96, L)])
    assert raw_lower_severe.severe_miles == raw_higher_severe.severe_miles == 8.0

    for order in ([raw_lower_severe, raw_higher_severe], [raw_higher_severe, raw_lower_severe]):
        result = rank_routes(order)
        assert result.routes[0].summary.route_id == "raw-8.04"
        assert result.recommendation.deciding_criterion == RankingCriterion.HIGH_MILES
        assert result.recommendation.reason == "Fewest High miles among the available routes."


def test_travel_time_decides_only_when_everything_else_ties():
    slow_but_safer = summary("slow", high=1.0, duration=10_000)
    fast_but_riskier = summary("fast", high=1.1, duration=5_000)
    assert rank_routes([fast_but_riskier, slow_but_safer]).routes[0].summary.route_id == "slow"

    tied_fast = summary("fast", high=1.0, duration=5_000)
    assert rank_routes([slow_but_safer, tied_fast]).routes[0].summary.route_id == "fast"


def test_ranks_and_labels():
    result = rank_routes([summary("c", severe=3), summary("a", severe=1), summary("b", severe=2)])
    assert [(r.summary.route_id, r.rank, r.label) for r in result.routes] == [
        ("a", 1, LABEL_RECOMMENDED),
        ("b", 2, LABEL_ALTERNATIVE),
        ("c", 3, LABEL_ALTERNATIVE),
    ]
    assert result.recommendation.no_safe_route is False


# --- Global warning ----------------------------------------------------------


def test_global_warning_only_when_every_route_has_no_travel_miles():
    all_unsafe = rank_routes([summary("a", no_travel=0.1), summary("b", no_travel=5.0)])
    assert all_unsafe.recommendation.no_safe_route is True
    assert all_unsafe.routes[0].label == LABEL_BEST_AVAILABLE_NOT_SAFE
    assert all(r.label != LABEL_RECOMMENDED for r in all_unsafe.routes)

    one_safe = rank_routes([summary("a", no_travel=0.1), summary("b", severe=40.0)])
    assert one_safe.recommendation.no_safe_route is False
    assert one_safe.routes[0].label == LABEL_RECOMMENDED


def test_global_warning_with_a_single_unsafe_route():
    result = rank_routes([summary("only", no_travel=2.0)])
    assert result.recommendation.no_safe_route is True
    assert result.routes[0].label == LABEL_BEST_AVAILABLE_NOT_SAFE


# --- Recommendation text -----------------------------------------------------


@pytest.mark.parametrize(
    ("winner", "runner_up", "text"),
    [
        (summary("w"), summary("l", no_travel=1.0), "Fewest No Travel miles among the available routes."),
        (summary("w", severe=8), summary("l", severe=9), "Fewest Severe miles among the available routes."),
        (summary("w", high=1), summary("l", high=2), "Fewest High miles among the available routes."),
        (summary("w", average=0.5), summary("l", average=0.6), "Lowest average risk among the available routes."),
        (
            summary("w", duration=10),
            summary("l", duration=20),
            "Same weather risk as the next route, with the shortest travel time.",
        ),
    ],
)
def test_reason_names_first_separating_value(winner, runner_up, text):
    reason = rank_routes([runner_up, winner]).recommendation.reason
    assert reason == text
    assert "%" not in reason


def test_reason_compares_against_runner_up_not_last_route():
    # Winner and runner-up tie on Severe miles; the third route has more.
    result = rank_routes([summary("c", severe=9), summary("w", severe=1, high=1), summary("r", severe=1, high=2)])
    assert result.recommendation.deciding_criterion == RankingCriterion.HIGH_MILES


def test_reason_for_single_route_and_full_tie():
    assert rank_routes([summary("only")]).recommendation.reason == REASON_SINGLE_ROUTE
    tie = rank_routes([summary("first"), summary("second")])
    assert tie.recommendation.reason == REASON_FULL_TIE
    assert tie.routes[0].summary.route_id == "first"


def test_rank_requires_routes():
    with pytest.raises(ValueError):
        rank_routes([])
