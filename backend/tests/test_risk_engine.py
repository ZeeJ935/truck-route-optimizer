import math

import pytest

from risk.engine import Hazard, RiskEngine
from risk.levels import RiskLevel

L, M, H, S, N = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)

# A light load never triggers a load rule.
LIGHT_LOAD = 10_000

engine = RiskEngine()


def test_risk_values_and_labels():
    assert [int(level) for level in RiskLevel] == [0, 1, 2, 3, 4]
    assert [level.label for level in RiskLevel] == ["Low", "Moderate", "High", "Severe", "No Travel"]


@pytest.mark.parametrize(
    ("wind", "expected"),
    [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, N), (80, N)],
)
def test_wind_tiers(wind, expected):
    assert engine.assess(wind, 0, 0, LIGHT_LOAD).level == expected


@pytest.mark.parametrize(
    ("rain", "expected"),
    [(0, L), (0.09, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H), (0.50, S), (1.00, S), (1.001, N)],
)
def test_rain_tiers(rain, expected):
    assert engine.assess(0, rain, 0, LIGHT_LOAD).level == expected


@pytest.mark.parametrize(
    ("snow", "expected"),
    [(0, L), (0.49, L), (0.50, M), (0.999, M), (1.00, H), (1.999, H), (2.00, S), (3.00, S), (3.001, N)],
)
def test_snow_tiers(snow, expected):
    assert engine.assess(0, 0, snow, LIGHT_LOAD).level == expected


@pytest.mark.parametrize(
    ("wind", "load", "expected"),
    [
        (35, 40_000, H),
        (35, 40_001, S),
        (44.9, 40_000, H),
        (44.9, 40_001, S),
        (45, 30_000, S),
        (45, 30_001, N),
        (47, 30_000, S),
        (47, 30_001, N),
        (54.9, 30_000, S),
        (54.9, 30_001, N),
        (55, 1, N),
    ],
)
def test_wind_and_load(wind, load, expected):
    assert engine.assess(wind, 0, 0, load).level == expected


@pytest.mark.parametrize("load", [1, 30_001, 40_001, 80_000])
@pytest.mark.parametrize("wind", [0, 24.9, 25, 34.9])
def test_load_does_not_change_low_or_moderate_wind(wind, load):
    assert engine.assess(wind, 0, 0, load).level == engine.assess(wind, 0, 0, LIGHT_LOAD).level


@pytest.mark.parametrize("load", [1, 30_001, 40_001, 80_000])
@pytest.mark.parametrize(
    ("rain", "snow"), [(0.10, 0), (0.25, 0), (0.50, 0), (1.001, 0), (0, 0.5), (0, 1.0), (0, 2.0), (0, 3.001)]
)
def test_load_does_not_change_rain_or_snow(rain, snow, load):
    light = engine.assess(0, rain, snow, LIGHT_LOAD)
    heavy = engine.assess(0, rain, snow, load)
    assert heavy.level == light.level
    assert heavy.reasons == light.reasons


def test_load_rule_reason_text():
    result = engine.assess(47, 0, 0, 30_001)
    assert result.level == N
    assert [reason.text for reason in result.reasons] == ["No Travel: wind 47 mph with load over 30,000 lb."]
    assert result.reasons[0].load_adjusted is True


def test_high_wind_load_reason_text():
    result = engine.assess(38.5, 0, 0, 40_001)
    assert result.reasons[0].text == "Severe: wind 38.5 mph with load over 40,000 lb."


def test_low_conditions_have_no_reasons():
    result = engine.assess(10, 0.01, 0, LIGHT_LOAD)
    assert result.level == L
    assert result.reasons == ()


def test_multiple_hazards_return_worst_and_keep_all_reasons():
    result = engine.assess(30, 0.6, 1.2, LIGHT_LOAD)
    assert result.level == S
    assert [(reason.hazard, reason.level) for reason in result.reasons] == [
        (Hazard.RAIN, S),
        (Hazard.SNOW, H),
        (Hazard.WIND, M),
    ]
    assert [reason.text for reason in result.reasons] == [
        "Severe: rain 0.6 in/hr.",
        "High: snow 1.2 in/hr.",
        "Moderate: wind 30 mph.",
    ]


def test_equal_levels_keep_wind_rain_snow_order():
    result = engine.assess(36, 0.3, 1.5, LIGHT_LOAD)
    assert result.level == H
    assert [reason.hazard for reason in result.reasons] == [Hazard.WIND, Hazard.RAIN, Hazard.SNOW]


def test_load_adjusted_wind_can_be_the_worst_hazard():
    result = engine.assess(46, 0.3, 0, 35_000)
    assert result.level == N
    assert result.reasons[0].hazard == Hazard.WIND


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -0.1, "5", True])
@pytest.mark.parametrize("position", [0, 1, 2])
def test_missing_or_invalid_weather_is_rejected_never_low(bad, position):
    values = [0.0, 0.0, 0.0]
    values[position] = bad
    with pytest.raises(ValueError):
        engine.assess(*values, LIGHT_LOAD)


@pytest.mark.parametrize("load", [0, -1, math.nan, math.inf, None])
def test_invalid_load_is_rejected(load):
    with pytest.raises(ValueError):
        engine.assess(0, 0, 0, load)
