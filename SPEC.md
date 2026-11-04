# Weather-Aware Truck Routing: Build Spec

This is the single source of truth for the Spotter Full Stack Developer assessment. It replaces all earlier prompts and corrections. Nothing here needs to be reinterpreted. If a real ambiguity remains, report it instead of silently deciding.

## How to use this file

- Work one phase at a time, in order. Do not start the next phase until the current phase's exit criteria pass.
- At the end of each phase, stop and give the phase report described in Part 4.
- Inspect the repository before writing code, and reuse anything suitable that already exists.
- Do not ask unnecessary questions. Stop only for a missing credential, a missing account, or a provider fact that contradicts this spec.
- Do not claim something works unless you ran it. Separate fake-provider test results from live API checks.

## Assessment summary

Build a React + Django web app that helps a truck driver choose the safest route based on weather, load weight, and travel time.

Scoring:

- 40%: routes, weather, risk, and recommendation logic
- 40%: UI, map, and heatmap smoothness and performance
- 15%: code quality
- 5%: documentation and walkthrough

The assessment says to prioritize correctness and clarity over extra features. Deliverables are a GitHub repository, a hosted application, and a 5-10 minute Loom walkthrough.

Never hardcode routes or weather, present fake data as real, or add features outside this spec.

---

# Part 1: Business Rules

## 1.1 Inputs

`POST /api/routes/analyze` accepts:

```json
{
  "origin": "Dallas, TX",
  "destination": "Denver, CO",
  "departure_time": "2026-11-03T08:00:00+05:00",
  "load_weight_lb": 40000,
  "sampling_interval_miles": 25
}
```

Validate on the frontend for usability and independently on the backend as the authority:

- Origin and destination are required, must geocode, and must not resolve to the same place.
- `departure_time` must be ISO 8601 with an explicit UTC offset, such as `+05:00` or `Z`. Reject offset-less timestamps. Never assume a time zone.
- Reject a departure more than 5 minutes in the past: accept only `departure >= now - 5 minutes`.
- Reject a departure outside the weather provider's supported forecast range.
- `load_weight_lb` must be a finite number greater than 0.
- `sampling_interval_miles` must be exactly 10, 25, or 50.

## 1.2 Weather risk tiers

Lower bounds are inclusive unless stated otherwise. Put these thresholds in one backend module. Do not use ambiguous chained comparisons.

Wind (mph):

| Range | Risk |
|---|---|
| `0 <= wind < 25` | Low |
| `25 <= wind < 35` | Moderate |
| `35 <= wind < 45` | High |
| `45 <= wind < 55` | Severe |
| `wind >= 55` | No Travel |

Rain (in/hr):

| Range | Risk |
|---|---|
| `rain < 0.10` | Low |
| `0.10 <= rain < 0.25` | Moderate |
| `0.25 <= rain < 0.50` | High |
| `0.50 <= rain <= 1.00` | Severe |
| `rain > 1.00` | No Travel |

Snow (in/hr):

| Range | Risk |
|---|---|
| `snow < 0.5` | Low |
| `0.5 <= snow < 1.0` | Moderate |
| `1.0 <= snow < 2.0` | High |
| `2.0 <= snow <= 3.0` | Severe |
| `snow > 3.0` | No Travel |

Rain of exactly 1.00 and snow of exactly 3.0 are Severe, not No Travel.

## 1.3 Load rules

These adjust wind risk only. Rain and snow are unaffected by load.

- `wind >= 55`: No Travel for any load.
- `45 <= wind < 55` and `load > 30,000 lb`: No Travel. Otherwise keep Severe.
- `35 <= wind < 45` and `load > 40,000 lb`: Severe. Otherwise keep High.

## 1.4 Checkpoint risk

1. Classify wind, rain, and snow separately.
2. Apply the load rules to the wind result.
3. The checkpoint's final risk is the worst of the three.
4. Keep every contributing reason, so the UI can show text such as "No Travel: wind 47 mph with load over 30,000 lb."

Numeric values: Low=0, Moderate=1, High=2, Severe=3, No Travel=4.

There must be one shared `RiskEngine`. Checkpoints and the heatmap both call it. Do not create separate calculators.

## 1.5 Checkpoints

Place checkpoints along the actual route geometry.

- Always include the origin at mile 0 and the destination at total route mileage.
- Place interior checkpoints at each multiple of the interval that is strictly less than the route length.
- Never duplicate the destination.

Examples at a 25-mile interval:

- 73-mile route: 0, 25, 50, 73
- 75-mile route: 0, 25, 50, 75
- 20-mile route: 0, 20

Each checkpoint stores: mile marker, latitude, longitude, ETA, represented segment miles, weather, risk, and reasons.

## 1.6 Segment representation

Each checkpoint represents the road halfway to each neighboring checkpoint:

- The first checkpoint covers from the origin to the midpoint with the next checkpoint.
- An interior checkpoint covers from the midpoint with the previous checkpoint to the midpoint with the next checkpoint.
- The final checkpoint covers from the midpoint with the previous checkpoint to the destination.

Invariant: segment miles sum to total route miles within a small tolerance, with no gaps, double-counting, or negative lengths.

## 1.7 ETA and forecast matching

All internal time logic uses UTC.

- Calculate each checkpoint ETA from the departure time and the provider's travel time along the route. Use the provider's most detailed durations, such as per-leg travel times, and interpolate by distance only within the smallest unit available.
- ETAs assume continuous driving at the provider's travel times, with no rest or fuel stops. Document this as an assumption.
- The frontend interprets the entered departure in the browser's time zone and sends that offset. Show every time for the trip in that same offset with a label, even when the route crosses time zones. Document this as an assumption.
- A forecast hour is eligible only if it is within 30 minutes of the target time.
- At an exact tie, use the earlier hour.
- If no hour is eligible, the target has no available forecast.

Examples:

| Target | Available hours | Result |
|---|---|---|
| 10:29 | 10:00, 11:00 | 10:00 |
| 10:30 | 10:00, 11:00 | 10:00 |
| 10:31 | 10:00, 11:00 | 11:00 |
| 10:31 | 10:00, 12:00 | None |

Never interpolate weather, repeat the last value, or substitute another checkpoint's weather.

If any checkpoint ETA on any final route has no eligible forecast, reject the whole analysis with a clear error. Never classify missing data as Low.

## 1.8 Route mileage and average risk

For each route:

- Sum raw segment miles for each risk tier, then round each total once.
- Round mileage to 0.1 mile using round-half-up.
- A nonzero mileage must round to at least 0.1, so 0.03 becomes 0.1.
- Use the same rounded mileage for ranking, status, the global warning, and display.

Average risk:

```text
average_risk = sum(raw_segment_miles * risk_value) / total_route_miles
```

Round it to 2 decimal places for ranking and display. Never use a simple checkpoint average.

## 1.9 Ranking

Compare routes lexicographically. Lower is better:

```text
(
  rounded_no_travel_miles,
  rounded_severe_miles,
  rounded_high_miles,
  rounded_average_risk,
  travel_time_seconds
)
```

Do not use a weighted score. Travel time is only the final tie-breaker.

`no_travel_miles` is an assumption added to the assessment's four criteria. Document it in the README: without it, a route with No Travel miles could beat a route with a small amount of Severe mileage.

The recommendation text must name the first ranking value that separated the winner from the runner-up. Do not invent percentages or other unsupported claims.

## 1.10 Route status

| Status | Condition |
|---|---|
| Not Safe | `no_travel_miles > 0` |
| Caution | `no_travel_miles = 0` and `severe_miles > 0` |
| Safe | `no_travel_miles = 0` and `severe_miles = 0` |

A route with High miles can be Safe, but its High miles must remain prominent.

The global warning appears only when every final route has `no_travel_miles > 0`. In that case, label the top route "Best available, not safe" rather than "Recommended" or "Safest."

## 1.11 Route selection

Run this order exactly:

1. Request up to 3 truck routes from the routing provider.
2. Deduplicate them.
3. Remove any route slower than 1.5x the fastest route's duration.
4. If fewer than 3 remain, try via-point alternatives, then repeat steps 2 and 3.
5. If more than 3 remain, keep the 3 fastest.
6. Run checkpoint, weather, and risk analysis only on these final routes.

Duplicate rule: sample both routes at the same spatial interval. Routes A and B are duplicates if either has at least 90% of its sampled points within 0.5 mile of the other. Do not rely on route IDs, names, distance, or duration. Keep the faster route from each duplicate pair.

Filtered routes must not affect forecast validation or appear in the results.

Never duplicate a route or alter geometry to make it look distinct. If fewer than 3 acceptable routes remain, return what exists and explain this in the response and UI, for example: "Only 2 distinct routes were available for this trip."

## 1.12 Forecast slider and heatmap

- The slider has 49 positions. Hour N equals `departure_time + N hours`, and hour 0 equals departure, not the current time.
- Show the actual date and time with a time zone label.
- `forecast.timestamps` always has 49 entries.
- Each corridor point's `risk` array also has 49 entries, aligned to those timestamps.
- Use `null` for an hour with no eligible forecast. Treat 0 as a valid Low value.
- Disable a slider hour when no corridor point has data for it, and explain why.
- Partial slider coverage is allowed only after all checkpoint forecasts succeed.
- Heatmap risk uses the same `RiskEngine` and the user's load weight.
- The backend calculates all risk values. After analysis, moving the slider must make zero network requests.
- Label the two time views clearly: checkpoints show weather at each ETA, while the heatmap shows the whole corridor at the selected time.

Corridor default, documented as an assumption: sample each final route every 25 miles, with one center point and one point 10 miles to each side. Reduce density evenly if the set exceeds 250 points (`CORRIDOR_MAX_POINTS` in `backend/analysis/limits.py`). Deduplicate shared points between routes.

Weather location budget per analysis (ceiling: 550 distinct locations, `MAX_WEATHER_LOCATIONS_PER_ANALYSIS`). Apply in this order:

1. Remove duplicate checkpoint locations across routes first.
2. Reserve at least 100 corridor locations so the heatmap is never empty.
3. Checkpoints may use the rest of the 550-location ceiling.
4. Give any budget left after checkpoints back to the corridor, up to 250.
5. If checkpoints still don't fit, reject the request with `validation_error` and suggest a larger sampling interval. Never drop checkpoints.

The 250-point cap replaces an earlier 600-point default. It comes from the measured Open-Meteo free limit. Each location in a request counts as one call, and the limit is 600 calls per minute per IP: a 7th 100-location request within one minute returned HTTP 429. A 600-point corridor plus checkpoints would not fit in one analysis.

## 1.13 Backend and frontend responsibilities

The backend alone calculates risk, risk mileage, average risk, route status, ranking, recommendation, and the global warning. It also generates the display text for reasons and recommendations.

The frontend renders those results and selects the forecast hour. It must not contain thresholds, load rules, or ranking logic. Mapping a risk value to a color or label is allowed.

## 1.14 User-requested addition: address suggestions

This was added at the user's request after the original specification.

- The Origin and Destination fields suggest places as the user types.
- A backend endpoint, `GET /api/places/suggest?q=`, calls TomTom's Places Search Suggest API with the existing server-side `TOMTOM_API_KEY`. There is no second key, and no key is exposed to the frontend.
- The frontend searches only after 3 or more characters, debounces requests by about 300 ms, cancels outdated requests, and caches repeat searches.
- Selection works with mouse, touch and keyboard, with accessible labels.
- Suggestions are optional: if they fail, the user can still type an address and run the analysis.

---

# Part 2: Technical Decisions

## 2.1 Providers

Hard constraint: use only free services that do not require a credit card or payment details. Never add payment details to an account, enable a paid plan, or choose a service that requires one. If a service asks for a card, stop and report it.

Defaults, to be rechecked in Phase 0:

| Purpose | Choice | Reason |
|---|---|---|
| Routing and geocoding | TomTom Routing API and Geocoding API on the free tier | `travelMode=truck`, `vehicleWeight` in kg, up to 5 alternatives, and no card |
| Weather | Open-Meteo free forecast API | Global hourly forecasts, batched coordinates, and no key or card |
| Map rendering | MapLibre GL JS with OpenFreeMap | Fast heatmap and line layers, with no key or registration. Show the required attribution |

HERE is not used because its sign-up requires billing details. OpenRouteService is not the default because its public API limits alternative routes to trips of about 100 km.

If TomTom's free key rejects truck routing, stop and report it. The first fallback to evaluate is OpenRouteService's `driving-hgv` profile, with distinct routes coming from via points for trips over 100 km. Keep this behind the `RoutingProvider` and `GeocodingProvider` interfaces.

Weather mapping:

- `wind_mph` comes from sustained 10 m wind (`wind_speed_10m`), not gusts.
- `rain_in_per_hour` equals `rain + showers`.
- `snow_in_per_hour` equals `snowfall`.
- Request explicit mph and inch units and UTC timestamps.
- Open-Meteo precipitation is a sum over the preceding hour. Treat that as the hourly rate and document it.

Routing weight: convert the entered load from lb to kg and send it as `vehicleWeight`. This is a lower bound on gross vehicle weight, so document that limitation. The risk rules always use the entered load.

All provider API keys stay server-side.

## 2.2 Backend

- Django with Django REST Framework. Keep it stateless with no database models unless one becomes necessary.
- Define `RoutingProvider`, `GeocodingProvider`, and `WeatherProvider` interfaces.
- Normalize provider responses before they reach business logic.
- Keep the risk engine, ranking, and checkpoint logic as pure, independently testable modules.
- Inject providers into services.
- The production wiring must use only real providers.
- Fake providers live only in test code. There must be no environment variable, flag, parameter, or endpoint that enables them.
- Batch weather requests, reuse results for identical rounded coordinates within one analysis, and use a short-lived server cache.
- Split weather batches to stay within the provider's URL and rate limits.
- Apply a short-lived server cache to geocoding and routing responses too, to protect the free quota.

Suggested structure:

```text
backend/
  config/
  api/
  routing/
  weather/
  risk/
  analysis/
  tests/
```

## 2.3 Frontend

- React, TypeScript, and Vite.
- MapLibre GL JS for the map.
- Keep API calls, map logic, state, and UI components separate.
- Update the heatmap with a paint expression or layer filter where possible, rather than rebuilding the data source on every slider movement.

Suggested structure:

```text
frontend/src/
  api/
  components/
  features/
  map/
  types/
  utils/
```

## 2.4 API response shape

```json
{
  "routes": [
    {
      "id": "route-1",
      "rank": 1,
      "label": "Recommended",
      "status": "CAUTION",
      "geometry": [[-96.80, 32.78]],
      "distance_miles": 382.0,
      "duration_seconds": 24120,
      "no_travel_miles": 0.0,
      "severe_miles": 8.0,
      "high_miles": 41.0,
      "average_risk": 0.74,
      "checkpoints": [
        {
          "mile": 25.0,
          "lat": 32.9,
          "lng": -97.2,
          "eta": "2026-11-03T04:30:00Z",
          "segment_miles": 25.0,
          "weather": {
            "forecast_time": "2026-11-03T05:00:00Z",
            "wind_mph": 18.2,
            "rain_in_per_hour": 0.02,
            "snow_in_per_hour": 0.0
          },
          "risk": 0,
          "risk_label": "Low",
          "reasons": []
        }
      ]
    }
  ],
  "recommendation": {
    "route_id": "route-1",
    "reason": "Fewest Severe miles among the available routes.",
    "no_safe_route": false
  },
  "route_notice": null,
  "forecast": {
    "timestamps": ["2026-11-03T03:00:00Z"],
    "corridor": [
      { "lat": 32.9, "lng": -97.2, "risk": [0] }
    ],
    "available_hours": [0],
    "notice": null
  }
}
```

Use stable error codes: `validation_error`, `geocoding_failed`, `no_route_found`, `forecast_unavailable`, `provider_rate_limited`, `provider_timeout`, and `provider_error`. Log details on the server. Never return stack traces or raw provider errors to the UI.

---

# Part 3: Phases

## Phase 0: Setup and provider check

Goal: confirm the plan works with real accounts before building on it.

Tasks:

1. Inspect the repository.
2. Create the backend and frontend skeletons, `.env.example`, `.gitignore`, and a short README stub.
3. Check current TomTom docs for truck parameters, `maxAlternatives` with `vehicleWeight`, `departAt`, geometry format, the most detailed travel times in the response, whether truck mode applies to each section, and the free quota. Check Open-Meteo for batch limits, rate limits, the forecast window, and terms of use.
4. Make one small live call to each provider using keys from local environment variables.
5. Confirm the hosting setup: Vercel's free plan for the frontend and Render's free web service for the backend, with no payment details on either account. Render's free service may sleep when idle, so the frontend must handle a slow first request.
6. Measure how an Open-Meteo multi-location request counts against its free limits, and report the weather locations and estimated calls per analysis.

Exit criteria:

- Both apps start.
- A health endpoint responds.
- One live route and one live forecast succeed.
- Any provider fact that contradicts this spec is reported.

## Phase 1: Business logic with no network calls

Goal: finish and prove the highest-value logic first.

Build the risk engine, load rules, checkpoint generation, segment allocation, forecast matching, mileage rounding, average risk, status, ranking, and global warning.

Required tests:

- Wind: 24.9 Low, 25 Moderate, 34.9 Moderate, 35 High, 44.9 High, 45 Severe, 54.9 Severe, 55 No Travel.
- Rain: 0.09 Low, 0.10 Moderate, 0.249 Moderate, 0.25 High, 0.499 High, 0.50 Severe, 1.00 Severe, 1.001 No Travel.
- Snow: 0.49 Low, 0.50 Moderate, 0.999 Moderate, 1.00 High, 1.999 High, 2.00 Severe, 3.00 Severe, 3.001 No Travel.
- Wind and load:
  - 35 + 40,000 = High
  - 35 + 40,001 = Severe
  - 44.9 + 40,000 = High
  - 44.9 + 40,001 = Severe
  - 45 + 30,000 = Severe
  - 45 + 30,001 = No Travel
  - 47 + 30,000 = Severe
  - 47 + 30,001 = No Travel
  - 54.9 + 30,000 = Severe
  - 54.9 + 30,001 = No Travel
  - 55 + 1 = No Travel
- Load does not change rain or snow risk.
- Multiple hazards return the worst level and keep all reasons.
- Each ranking value decides correctly when all earlier values tie.
- Fewer No Travel miles beat fewer Severe miles.
- Travel time decides only when everything else ties.
- 0.03 No Travel miles becomes 0.1, makes the route Not Safe, and ranks below a route with 0.0.
- Status: Not Safe, Caution, and Safe, including that High miles alone do not make a route unsafe.
- Global warning: shown only when all routes have No Travel miles.
- Distance weighting: 100 Low + 10 Severe differs from 10 Low + 100 Severe.
- Checkpoints: all three intervals, routes shorter than, equal to, slightly above, and exact multiples of the interval, and long routes.
- Segment miles sum to route miles in each of those cases.
- Forecast matching: all examples from section 1.7.

Exit criteria:

- All tests pass with no network access.

## Phase 2: Providers and route selection

Goal: turn real provider responses into normalized routes.

Build the provider interfaces, TomTom and Open-Meteo implementations, normalization, unit conversion, route deduplication, the 1.5x filter, and via-point fallback.

Required tests with injected fakes:

- 3 distinct routes return 3.
- Duplicate routes with different IDs are removed, and the faster one is kept.
- Clearly different routes stay separate.
- A via-point route over 1.5x is rejected.
- Via-point fallback runs when fewer than 3 routes remain.
- 2 or 1 acceptable routes return honestly with a notice.
- More than 3 acceptable routes keep the 3 fastest.
- Provider timeout, rate limit, and malformed responses map to the correct errors.
- Weather unit conversion is correct.

Exit criteria:

- Tests pass.
- A live short trip and a live long trip produce normalized routes with accurate geometry.
- Report how often TomTom returned 3 routes without fallback.

## Phase 3: Analysis API

Goal: complete the backend workflow.

Build the analysis service and `POST /api/routes/analyze`. Run the order from section 1.11, then checkpoints, ETAs, forecast matching, risk, ranking, and heatmap data.

Required tests:

- Past departure beyond 5 minutes is rejected, and one inside the grace period is accepted.
- Offset-less timestamps are rejected.
- `Z` and `+05:00` timestamps are accepted and calculated in UTC.
- Invalid interval, invalid load, and missing fields are rejected.
- Weather requests use checkpoint ETAs, not the departure time.
- Missing forecast on a final route rejects the analysis.
- Missing forecast on a filtered route has no effect.
- Heatmap and checkpoint risk use the same `RiskEngine`.
- The heatmap has 49 timestamps and 49 aligned risk values, with `null` for missing hours.
- Hour 0 equals departure and hour N equals departure plus N hours.
- Fake providers cannot be reached from production wiring.

Exit criteria:

- Tests pass.
- A live API call returns a complete response.
- Record the response size, analysis time, TomTom request count, and weather locations for a long route at each interval, then optimize if needed.

## Phase 4: Frontend workflow

Goal: make the result understandable within seconds.

Build the form, loading and error states, recommendation panel, global warning, route comparison, route selection, and checkpoint list. Use a clean product-style layout: a left panel for input and results, with the map as the main workspace.

Each route must show its rank, label, status, distance, travel time, No Travel miles, Severe miles, High miles, and average risk.

If the first request is slow because the free backend is waking up, show a clear message that it can take up to a minute. Use a client timeout long enough to survive this.

Required tests:

- Frontend validation works and backend errors display clearly.
- The UI renders backend decisions without recalculating them.
- The global warning follows the backend value.
- "Best available, not safe" replaces normal recommendation wording in the warning state.
- A route notice appears when fewer than 3 routes are returned.

Exit criteria:

- The full workflow works with the live backend.
- Type checks, lint, and tests pass.

## Phase 5: Map

Goal: make routes and dangerous sections obvious.

Show all routes, a clearly emphasized selected route, the recommended route, origin and destination markers, and checkpoints colored by risk. Hovering or clicking a checkpoint must show ETA with time zone, mile marker, wind, rain, snow, risk, and reasons. Selecting a route in the panel or on the map must keep both in sync.

Exit criteria:

- Route switching does not refetch data.
- Map interactions stay smooth with 10-mile sampling on a long route.
- Risk is communicated with text as well as color.
- The layout works on desktop and remains usable on narrow screens.

## Phase 6: Heatmap and forecast slider

Goal: finish the highest-risk UI requirement.

Build the corridor heatmap, 0-48 hour slider, selected date and time label, disabled-hour display, and explanatory notice. Use a color scale that matches the risk levels.

Required tests:

- The slider selects the correct hour index.
- Moving it makes zero network requests.
- Disabled hours cannot be selected.
- `null` is treated as missing and 0 as Low.

Exit criteria:

- Dragging the slider feels immediate on the largest supported payload.
- The network panel shows zero requests during slider use.
- The heatmap changes when real forecast data changes across hours.

## Phase 7: Hardening, documentation, and deployment

Goal: submit a verifiable, reviewable project.

Tasks:

1. Remove dead code and unused dependencies.
2. Write the README: overview, architecture, stack, setup, environment variables, commands, API, risk rules, ranking, assumptions, testing, deployment, and limitations.
3. Configure production settings, CORS, HTTPS, API URL settings, static assets, and logging.
4. Deploy the frontend and backend. Run the deployed backend through Gunicorn using `backend/gunicorn.conf.py` (120-second worker timeout).
5. Run the complete checks below.

Automated checks:

- Run all backend and frontend tests.
- Run lint and type checks.
- Run the production build.

Live checks, using real APIs:

- A short route shorter than the sampling interval
- Each sampling interval on a normal trip
- A long route
- Three distinct routes, or the honest fewer-route message
- Correct checkpoint positions and ETAs
- Weather using the forecast hour matched to each ETA
- Risk, ranking, and status on real results
- Route switching and checkpoint details
- Heatmap and slider, with zero slider network requests
- Time zone labels
- Invalid input
- A clean browser session on the deployed app
- A long analysis on the deployed backend completes under Gunicorn without a worker timeout

Scenarios that require controlled weather, such as exact boundaries, all routes having No Travel miles, and forced provider failures, must be proven with fake-provider tests and reported as such.

Exit criteria:

- All checks pass or are explicitly reported as unverified.
- The deployed app works from a clean browser session.
- The deployed backend runs under Gunicorn, and a long analysis completes without a worker timeout.
- Every known limitation is in the README.

---

# Part 4: Reporting

## At the end of each phase

Report:

- What was completed
- Tests run and their results
- Live checks run and their results
- Any issues, provider limits, or assumptions
- Whether the exit criteria passed

Then stop and wait for approval.

## Final report

Include:

1. What was implemented
2. Architecture
3. Providers and why they were chosen
4. Risk calculation approach
5. Recommendation algorithm
6. Automated tests, including which used fake providers
7. Live checks and the exact behaviors verified
8. Provider limitations
9. Known limitations
10. Remaining assumptions
11. Confirmation that fake providers are isolated from production
12. Confirmation that the backend owns business decisions
13. Confirmation that the heatmap uses the same risk engine
14. Exact local run commands
15. Required environment variables
16. Deployment instructions
17. A 5-10 minute Loom outline
18. A clear statement of whether every assessment requirement was implemented

Do not write "fully verified" unless the matching checks were actually performed.
