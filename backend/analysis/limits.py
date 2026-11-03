"""Analysis-wide limits and defaults, kept in one module.

Risk thresholds and load rules live in ``risk/thresholds.py``; this module holds
everything else the analysis needs as a named constant.
"""

from datetime import timedelta

# Checkpoint sampling intervals the API accepts, in miles.
ALLOWED_SAMPLING_INTERVALS_MILES: tuple[int, ...] = (10, 25, 50)

# A forecast hour is eligible for a target time only within this distance of it.
FORECAST_MATCH_WINDOW = timedelta(minutes=30)

# A departure may be at most this far in the past when the request arrives.
PAST_DEPARTURE_GRACE = timedelta(minutes=5)

# The heatmap slider covers departure + 0 .. departure + 48 hours (49 positions).
FORECAST_SLIDER_HOURS = 48
FORECAST_SLIDER_POSITIONS = FORECAST_SLIDER_HOURS + 1

# Heatmap corridor: one center point every CORRIDOR_SPACING_MILES along each route,
# plus one point CORRIDOR_SIDE_OFFSET_MILES to each side of the route.
CORRIDOR_SPACING_MILES = 25.0
CORRIDOR_SIDE_OFFSET_MILES = 10.0

# Corridor points are thinned evenly above this cap.
# SPEC.md suggested 600, but Open-Meteo counts each location as one call and
# allows 600 calls per minute per IP (measured: the 7th 100-location request in
# one minute returned HTTP 429). 600 corridor points plus checkpoints would not
# fit in one analysis, so the cap is lowered.
CORRIDOR_MAX_POINTS = 250

# Hard ceiling on distinct weather locations (checkpoints + corridor) requested
# by one analysis. It keeps one analysis inside Open-Meteo's 600 calls/minute
# limit with a margin for retries and concurrent requests.
MAX_WEATHER_LOCATIONS_PER_ANALYSIS = 550
