"""Every weather-risk threshold and load rule, in one place.

Lower bounds are inclusive. Rain and snow have an inclusive Severe upper bound:
rain of exactly 1.00 in/hr and snow of exactly 3.0 in/hr are Severe, and only
values strictly above them are No Travel.
"""

# Wind, sustained 10 m wind speed in mph. Each value is the inclusive lower
# bound of its level.
WIND_MODERATE_MIN_MPH = 25.0
WIND_HIGH_MIN_MPH = 35.0
WIND_SEVERE_MIN_MPH = 45.0
WIND_NO_TRAVEL_MIN_MPH = 55.0

# Rain in inches per hour. Lower bounds are inclusive; the Severe upper bound is inclusive.
RAIN_MODERATE_MIN_IN_HR = 0.10
RAIN_HIGH_MIN_IN_HR = 0.25
RAIN_SEVERE_MIN_IN_HR = 0.50
RAIN_SEVERE_MAX_IN_HR = 1.00

# Snow in inches per hour. Lower bounds are inclusive; the Severe upper bound is inclusive.
SNOW_MODERATE_MIN_IN_HR = 0.5
SNOW_HIGH_MIN_IN_HR = 1.0
SNOW_SEVERE_MIN_IN_HR = 2.0
SNOW_SEVERE_MAX_IN_HR = 3.0

# Load rules. They adjust wind risk only, and a load must be strictly above the limit.
# Severe wind (45 to under 55 mph) with load above this becomes No Travel.
SEVERE_WIND_LOAD_LIMIT_LB = 30_000.0
# High wind (35 to under 45 mph) with load above this becomes Severe.
HIGH_WIND_LOAD_LIMIT_LB = 40_000.0
