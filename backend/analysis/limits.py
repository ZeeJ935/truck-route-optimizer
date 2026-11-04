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

# --- Route selection -----------------------------------------------------------

# Number of final routes compared, and the routing request for up to that many.
MAX_ROUTES = 3
PROVIDER_MAX_ALTERNATIVES = MAX_ROUTES - 1

# Routes slower than this multiple of the fastest route's duration are removed.
MAX_DURATION_RATIO = 1.5

# Duplicate detection: both routes are sampled at the same spatial interval, and
# they are duplicates if either has at least DUPLICATE_MIN_SHARED_FRACTION of its
# samples within DUPLICATE_MAX_DISTANCE_MILES of the other.
DUPLICATE_SAMPLE_INTERVAL_MILES = 0.25
DUPLICATE_MAX_DISTANCE_MILES = 0.5
DUPLICATE_MIN_SHARED_FRACTION = 0.9

# Via-point fallback: perpendicular offsets from the midpoint of the straight
# origin-destination line, as fractions of that line's length, tried in order.
VIA_OFFSET_FRACTIONS: tuple[float, ...] = (0.15, -0.15, 0.30, -0.30)

# --- Providers -------------------------------------------------------------------

PROVIDER_TIMEOUT_SECONDS = 20.0
GEOCODE_CACHE_TTL_SECONDS = 60 * 60
ROUTE_CACHE_TTL_SECONDS = 10 * 60
WEATHER_CACHE_TTL_SECONDS = 15 * 60

# Weather locations per Open-Meteo request (about a 2 KB URL at 100).
WEATHER_BATCH_SIZE = 100

# Coordinates are rounded to this many decimals (about 0.7 mile) before weather
# lookup; identical rounded coordinates are requested once per analysis.
WEATHER_COORD_DECIMALS = 2

# Open-Meteo forecasts reach 16 days ahead.
WEATHER_FORECAST_HORIZON_DAYS = 16

# --- Analysis -------------------------------------------------------------------

# The corridor always keeps at least this many weather locations, so the heatmap
# is never empty; checkpoints may use the rest of MAX_WEATHER_LOCATIONS_PER_ANALYSIS.
CORRIDOR_MIN_RESERVED_POINTS = 100
MAX_CHECKPOINT_LOCATIONS = MAX_WEATHER_LOCATIONS_PER_ANALYSIS - CORRIDOR_MIN_RESERVED_POINTS

# Origin and destination closer than this are treated as the same place.
SAME_PLACE_MAX_MILES = 0.5

# Longest accepted origin or destination text.
MAX_PLACE_QUERY_LENGTH = 200

# --- Time budget -----------------------------------------------------------------

# An analysis must finish well inside the 120 s Gunicorn worker timeout and the
# 120 s frontend timeout, leaving room for serialization and transfer.
ANALYSIS_TIME_BUDGET_SECONDS = 100

# After an Open-Meteo 429, wait this long, then retry the unfinished batches once.
WEATHER_RETRY_DELAY_SECONDS = 30
# Time reserved for the retried requests themselves when checking the budget.
WEATHER_RETRY_MARGIN_SECONDS = 15

# --- Place suggestions (origin and destination typeahead) ------------------------

# Searches start at this many characters; longer input is rejected.
PLACE_SUGGEST_MIN_CHARS = 3
PLACE_SUGGEST_MAX_CHARS = 100
PLACE_SUGGEST_MAX_RESULTS = 5
# Suggestions are limited to these countries (ISO 3166-1 alpha-2). The app is built
# for US trucking (mph, inches, pounds); add codes here to widen it.
PLACE_SUGGEST_COUNTRIES: tuple[str, ...] = ("US",)
PLACE_SUGGEST_CACHE_TTL_SECONDS = 60 * 60
PLACE_SUGGEST_TIMEOUT_SECONDS = 8.0
# Per-client request limit for the public suggest endpoint, protecting the free quota.
PLACE_SUGGEST_RATE = "60/min"

# --- Abuse protection ---------------------------------------------------------------

# Per-client analysis limits (checked before any provider call).
ANALYZE_RATE_PER_MINUTE = "6/min"
ANALYZE_RATE_PER_DAY = "60/day"

# App-wide cap on uncached Open-Meteo locations per UTC day (free limit is 10,000).
# An analysis is refused up front if the worst case (MAX_WEATHER_LOCATIONS_PER_ANALYSIS)
# would pass it. Kept in memory: it resets when the server restarts.
WEATHER_DAILY_LOCATION_CAP = 8_000
