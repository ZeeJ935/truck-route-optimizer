"""Unit conversions."""

METERS_PER_MILE = 1609.344
KG_PER_LB = 0.45359237


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE


def lb_to_kg(pounds: float) -> int:
    """Pounds to whole kilograms, as TomTom's vehicleWeight expects."""
    return round(pounds * KG_PER_LB)
