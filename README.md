# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest route based on weather, load weight, and travel time.

The driver enters an origin, a destination, a departure time, and a load weight. The backend compares up to three truck routes. It samples the forecast at each checkpoint for the time the truck is expected to arrive there, scores the weather risk with load-aware rules, and recommends a route. The frontend shows the routes, checkpoints, and a forecast heatmap along the trip corridor.

## Architecture

```text
┌──────────────────────┐        HTTPS/JSON        ┌───────────────────────────────┐
│  React + TypeScript  │  ───────────────────▶    │  Django REST API (stateless)  │
│  (Vite, MapLibre)    │                          │                               │
│  renders decisions,  │  ◀───────────────────    │  api/       HTTP layer        │
│  selects map hour    │                          │  analysis/  orchestration and │
└──────────────────────┘                          │             pure route logic  │
                                                  │  risk/      RiskEngine        │
                                                  │  routing/   TomTom provider   │
                                                  │  weather/   Open-Meteo        │
                                                  └───────────────────────────────┘
```

- **The backend owns every business decision.** It calculates risk, mileage by risk tier, average risk, route status, ranking, the recommendation, and the global warning. It also writes the display text for reasons and recommendations.
- **The frontend only renders those results.** It holds no thresholds, load rules, or ranking logic. It maps risk values to colours and labels, and selects the forecast hour.
- **Frontend validation is for usability only.** The frontend checks required fields, a departure that isn't in the past, a positive load, and the interval. The backend validates every request again and is the authority. Backend field errors appear under the matching inputs.
- **Switching routes makes no network request.** Changing the selected route uses data already loaded.
- **One shared `RiskEngine`.** Checkpoints and the heatmap both use `risk/engine.py`. Every threshold lives in `risk/thresholds.py`.
- **Pure logic modules.** Checkpoint placement, ETAs, forecast matching, and scoring have no I/O or framework code, so they are tested without the network.
- **Provider interfaces.** Routing, geocoding, and weather providers sit behind interfaces and are injected into services. Provider responses are normalised before they reach business logic. API keys stay on the server.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, Django 6.1, Django REST Framework (no database) |
| Frontend | React 19, TypeScript, Vite |
| Routing and geocoding | TomTom Routing API (`travelMode=truck`) and Geocoding API |
| Weather | Open-Meteo forecast API |
| Map | MapLibre GL JS with OpenFreeMap tiles |
| Hosting | Vercel (frontend), Render (backend) |

## Project structure

```text
backend/
  config/      Django settings and root URLs
  api/         HTTP endpoints
  analysis/    route selection, checkpoints, ETAs, forecast matching, scoring, limits
  core/        stable service errors, HTTP helper, TTL cache, unit conversions
  risk/        risk levels, thresholds, RiskEngine
  routing/     provider interfaces, normalization, TomTom implementation
  weather/     provider interface, Open-Meteo implementation
  tests/       pytest suite (network blocked; fake providers live only here)
frontend/
  src/
    api/         API client
    components/  UI components
    features/    feature modules
    map/         map logic
    types/       shared types
    utils/       helpers
```

## Getting started

Prerequisites: Python 3.13 or newer, and Node 20 or newer.

1. Copy `.env.example` to `.env` in the repo root. Set `TOMTOM_API_KEY` and `DJANGO_DEBUG=true`.

2. Start the backend:

   ```bash
   cd backend
   python -m venv .venv
   .venv/Scripts/activate          # Windows
   # source .venv/bin/activate     # macOS / Linux
   pip install -r requirements-dev.txt
   python manage.py runserver 127.0.0.1:8000
   ```

3. Start the frontend in a second terminal:

   ```bash
   cd frontend
   npm install
   npm run dev                     # http://localhost:5173 (proxies /api to :8000)
   ```

## Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `TOMTOM_API_KEY` | backend | TomTom routing and geocoding key |
| `DJANGO_SECRET_KEY` | backend | Required when `DJANGO_DEBUG` is not `true` |
| `DJANGO_DEBUG` | backend | `true` for local development only |
| `ALLOWED_HOSTS` | backend | Comma-separated host names |
| `CORS_ALLOWED_ORIGINS` | backend | Comma-separated frontend origins |
| `VITE_API_BASE_URL` | frontend | Backend base URL. Leave it empty locally |

Never commit `.env`. See `.env.example` for a template.

## Tests and checks

```bash
# Backend
cd backend
pytest                # unit tests; any network access fails the test

# Frontend
cd frontend
npm test              # Vitest + Testing Library; fetch is mocked
npm run typecheck
npm run lint
npm run build         # type check + production build
```

## Running in production

The backend runs under Gunicorn with the settings in `backend/gunicorn.conf.py`:

```bash
cd backend
gunicorn config.wsgi:application -c gunicorn.conf.py
```

- **Worker timeout.** It is 120 seconds. A long analysis takes 10–20 seconds, and a free instance that has been sleeping can need up to a minute to wake.
- **Workers.** One worker with 4 threads, so the in-memory provider caches are shared and memory stays low.
- **Frontend timeout.** The frontend waits up to 120 seconds for an analysis, matching the server.
- **Waiting state.** While waiting, it shows a spinner and the real elapsed time, with no estimated progress. After 10 seconds it explains that the server may be waking up and that this can take up to a minute.
- **Server log.** Each analysis logs one line with the time spent per stage (geocoding, routing, via attempts, weather, risk, ranking, serialization) and counts. The line never includes place names, URLs or keys.

## API

### `GET /api/health`

Returns the service status.

```json
{ "status": "ok" }
```

### `POST /api/routes/analyze`

Request:

```json
{
  "origin": "Dallas, TX",
  "destination": "Denver, CO",
  "departure_time": "2026-11-03T08:00:00+05:00",
  "load_weight_lb": 40000,
  "sampling_interval_miles": 25
}
```

| Field | Rule |
|---|---|
| `origin`, `destination` | Required text, up to 200 characters. Both must geocode and must not resolve to the same place (within 0.5 mile). |
| `departure_time` | ISO 8601 with an explicit offset (`+05:00` or `Z`). No earlier than 5 minutes ago and no later than the last forecast hour (16 days ahead). |
| `load_weight_lb` | A number greater than 0. |
| `sampling_interval_miles` | Exactly `10`, `25`, or `50`. |

Response (abridged; all times are UTC, geometry is `[lng, lat]`):

```json
{
  "routes": [
    {
      "id": "route-1", "rank": 1, "label": "Recommended", "status": "CAUTION",
      "geometry": [[-96.79622, 32.77798]],
      "distance_miles": 883.4, "duration_seconds": 43872,
      "no_travel_miles": 0.0, "severe_miles": 8.0, "high_miles": 41.0, "average_risk": 0.74,
      "checkpoints": [
        {
          "mile": 25.0, "lat": 32.9, "lng": -97.2, "eta": "2026-11-03T04:30:00Z", "segment_miles": 25.0,
          "weather": { "forecast_time": "2026-11-03T05:00:00Z", "wind_mph": 18.2, "rain_in_per_hour": 0.02, "snow_in_per_hour": 0.0 },
          "risk": 0, "risk_label": "Low", "reasons": []
        }
      ]
    }
  ],
  "recommendation": { "route_id": "route-1", "reason": "Fewest Severe miles among the available routes.", "no_safe_route": false },
  "route_notice": null,
  "forecast": {
    "timestamps": ["2026-11-03T03:00:00Z", "... 49 entries ..."],
    "corridor": [{ "lat": 32.9, "lng": -97.2, "risk": [0, 0, 1, null, "... 49 entries ..."] }],
    "available_hours": [0, 1, 2],
    "notice": null
  }
}
```

- `forecast.timestamps[N]` is departure + N hours, for N from 0 to 48.
- Each corridor `risk` array lines up with `forecast.timestamps`. `null` means no forecast for that hour, and `0` means Low.
- Responses are gzip-compressed when the client accepts it.

Errors use one envelope: `{"error": {"code": "...", "message": "...", "fields": {...}}}`. `fields` appears only on validation errors.

| Code | HTTP | When |
|---|---|---|
| `validation_error` | 400 | Invalid input, malformed JSON, same origin and destination, or too many checkpoints for the weather budget |
| `geocoding_failed` | 422 | A place could not be found |
| `no_route_found` | 422 | No truck route exists between the places |
| `forecast_unavailable` | 422 | A checkpoint ETA on a final route has no eligible forecast hour |
| `provider_rate_limited` | 503 | A provider rate-limited the request. Includes `Retry-After: 60` |
| `provider_timeout` | 504 | A provider did not respond in time |
| `provider_error` | 502 | A provider failed or returned an unexpected response |
| `internal_error` | 500 | An unexpected server error. Details are logged on the server only |

Error messages never contain stack traces or raw provider responses.

## Risk rules

Each checkpoint's wind, rain, and snow are classified separately. Lower bounds are inclusive.

| Level (value) | Wind (mph) | Rain (in/hr) | Snow (in/hr) |
|---|---|---|---|
| Low (0) | < 25 | < 0.10 | < 0.5 |
| Moderate (1) | 25 – < 35 | 0.10 – < 0.25 | 0.5 – < 1.0 |
| High (2) | 35 – < 45 | 0.25 – < 0.50 | 1.0 – < 2.0 |
| Severe (3) | 45 – < 55 | 0.50 – 1.00 | 2.0 – 3.0 |
| No Travel (4) | ≥ 55 | > 1.00 | > 3.0 |

Load rules adjust wind risk only:

- Wind of 55 mph or more is No Travel for any load.
- Wind of 45 to under 55 mph with a load over 30,000 lb is No Travel.
- Wind of 35 to under 45 mph with a load over 40,000 lb is Severe.

A checkpoint's risk is the worst of the three hazards. A reason is kept for every hazard above Low, for example "No Travel: wind 47 mph with load over 30,000 lb." Missing or invalid weather is rejected; it is never treated as Low.

## Route selection

1. Request up to 3 truck routes from TomTom: the fastest route plus 2 alternatives.
2. Remove duplicates. Both routes are sampled every 0.25 mile, and they are duplicates if either has at least 90% of its samples within 0.5 mile of the other. The faster route of each duplicate pair is kept. Route IDs, distance and duration are never used to detect duplicates.
3. Remove any route that takes more than 1.5 times as long as the fastest route.
4. If fewer than 3 routes remain, request routes through via points. A via point is offset sideways from the midpoint of the straight origin-destination line, at 15% and then 30% of that line's length, on each side. Steps 2 and 3 are repeated after each via route. A via point that cannot be routed (for example, one in water) is skipped.
5. If more than 3 routes remain, keep the 3 fastest.

Routes are never copied or altered to look distinct. When fewer than 3 routes remain, the response says so, for example: "Only 2 distinct routes were available for this trip."

Via-point attempts are optional extras. If one times out or fails after a route has already been accepted, the failure is logged, that attempt is skipped, and the accepted routes are kept. If the routing provider rate-limits a via attempt, no further via attempts are made. Only a failure of the first routing request fails the analysis.

## Weather window and location budget

- **Forecast window.** One weather request batch covers every checkpoint ETA, even ETAs more than 48 hours after departure, plus the 48-hour heatmap window. The window is widened by the 30-minute match rule and clamped to the provider's last forecast hour. The heatmap slider always covers hours 0 to 48 only.
- **Missing forecasts.** If any checkpoint ETA on a final route has no eligible forecast hour, the analysis fails with `forecast_unavailable`. An hour with any missing value counts as missing, never as Low.
- **Location budget.** Open-Meteo counts each location as one call, so one analysis requests at most 550 distinct locations. The budget is applied in this order:
  1. Remove duplicate checkpoint locations across routes first. Coordinates are rounded to 2 decimals.
  2. Reserve at least 100 corridor locations, so the heatmap is never empty.
  3. Checkpoints may use the rest of the 550-location ceiling, which is up to 450.
  4. Any budget left after checkpoints goes back to the corridor, up to 250. Corridor points are thinned evenly to fit.
  5. If the checkpoints still don't fit, the request is rejected with `validation_error`, and the message suggests a larger sampling interval. Checkpoints are never dropped.
- **Heatmap corridor.** Each route gets a point every 25 miles, plus one 10 miles to each side, perpendicular to the direction of travel. Points shared between routes are counted once.
- **Rate limits.** Open-Meteo's published free limit is 600 calls per minute, and each location in a request counts as one call. So two long analyses in a row can go over the limit.
  - If Open-Meteo returns HTTP 429, the analysis waits about 30 seconds and retries once. Only the unfinished batches are retried; batches already received are never requested again.
  - The retry only happens if the whole analysis can still finish within its 100-second budget, which is inside the 120-second server and browser limits.
  - If the retry is also rate-limited, the analysis fails with `provider_rate_limited` and asks the user to try again in about a minute.
  - So a second long analysis started right after another may wait about 30 seconds, or fail with that message.
- **Waiting message.** While a retry is waiting, the browser keeps showing the real elapsed time. After 30 seconds it adds that a busy weather or routing service can add up to a minute.

## Distance basis

Each route uses one distance basis: the provider's route length. The provider's geometry distances and travel-time progress distances are scaled so both end at exactly that length. Checkpoint miles, segment miles, ETAs and route totals therefore always agree, even though the length measured along the geometry differs slightly from the road length. In live checks the two differed by less than 0.2%.

## Checkpoints and ETAs

- **Checkpoint placement.** Checkpoints sit on the route geometry: at mile 0, at every multiple of the sampling interval (10, 25, or 50 miles) below the route length, and at the destination.
- **Represented road.** Each checkpoint represents the road halfway to each neighbouring checkpoint, so the represented miles always add up to the route length.
- **ETAs.** Each checkpoint's ETA comes from the departure time plus the provider's cumulative travel time. Time is interpolated by distance only between the provider's two nearest progress entries.
- **Forecast matching.** A forecast hour is used only if it is within 30 minutes of the ETA, and an exact tie picks the earlier hour. If no hour is eligible, the analysis is rejected; weather is never interpolated or borrowed.

## Ranking and recommendation

For each route, the raw represented miles are summed per risk tier and rounded once. Rounding is to 0.1 mile, half-up, and any nonzero total shows at least 0.1. Average risk is distance-weighted, then rounded to 2 decimals:

```text
average_risk = sum(segment_miles × risk_value) / route_miles
```

Routes are compared on these values in order, and lower is better:

```text
(no_travel_miles, severe_miles, high_miles, average_risk, travel_time_seconds)
```

Each route also gets a status:

| Status | Condition |
|---|---|
| Not Safe | No Travel miles > 0 |
| Caution | No Travel miles = 0 and Severe miles > 0 |
| Safe | No Travel miles = 0 and Severe miles = 0. High miles are still shown |

- The top route is labelled **Recommended**, and the others are labelled **Alternative**.
- If every route has No Travel miles, a global warning is shown and the top route is labelled **Best available, not safe**.
- The recommendation reason names the first ranking value that separated the winner from the runner-up.

## Map

The map uses MapLibre GL JS with OpenFreeMap's Positron basemap, which needs no key. It shows OpenFreeMap, OpenMapTiles and OpenStreetMap attribution, and "Weather: Open-Meteo.com (CC BY 4.0)".

- **Routes.** Every route is drawn.
  - The selected route is a thick blue line with a white casing, always drawn above the other routes. So on shared highways the selected route stays visible.
  - The top-ranked route, when not selected, is a dashed green line, labelled with its backend label ("Recommended", or "Best available, not safe").
  - The other routes are muted grey.
- **Hazard sections.** Each Severe or No Travel checkpoint on the selected route colours the road it represents: from the midpoint with the previous checkpoint to the midpoint with the next one. Severe is red and No Travel is purple, with a dark outline. Neighbouring sections of the same level are merged.
- **Checkpoints.** The selected route's checkpoints are dots coloured by risk. They are smaller at overview zoom, so the line stays visible at 10-mile spacing, and Severe or No Travel dots stay larger. Hovering a dot shows its ETA and forecast hour with the time-zone label, mile, wind, rain, snow, risk and reasons. Clicking pins the popup.
- **Markers.** "A" marks the origin and "B" the destination.
- **Legend.** It describes every colour in text. It is collapsible and starts collapsed on narrow screens.
- **Selection.** Clicking a route on the map selects it in the panel, and selecting a card in the panel highlights the route on the map. Switching only changes map filters; it makes no network request and doesn't move the view.
- **Fitting.** The view fits all routes after each analysis.
- **Performance.** Measured on the largest response (Dallas to Denver at 10-mile sampling, about 32,000 route points), with no geometry simplification:
  - route switches took 36–54 ms
  - panning and zooming produced no main-thread long tasks
  - no frame took longer than 8 ms

  The drawn lines therefore use the full route geometry.
- **Loading.** MapLibre loads as a separate chunk after the form and results, and its web worker is served as its own asset.

## Assumptions

- **No Travel miles come first in the ranking.** The brief lists Severe miles, High miles, average risk, and travel time. No Travel miles are added in front of these; otherwise a route with No Travel miles could beat a route with a small amount of Severe mileage.
- **Continuous driving.** ETAs assume continuous driving at the provider's travel times, with no rest or fuel stops.
- **Time zones.** The departure is read in the browser's time zone and sent with its UTC offset. Every trip time is shown in that same offset, with a label, even when the route crosses time zones. The backend works in UTC.
- **Vehicle weight.** The entered load is converted from lb to kg and sent to TomTom as `vehicleWeight`. This is a lower bound on gross vehicle weight, because the truck's own weight is unknown. The risk rules always use the entered load.
- **Weather values.** Open-Meteo's `rain`, `showers`, and `snowfall` are totals for the preceding hour. They are used as the hourly rate. Rain is `rain + showers`, and wind is the sustained 10 m wind speed, not gusts.
- **Heatmap corridor.** Each route is sampled every 25 miles, with one centre point and one point 10 miles to each side. Points shared between routes are deduplicated.
- **Weather location limits.** The corridor is capped at 250 points, and one analysis requests at most 550 distinct weather locations (`backend/analysis/limits.py`). Open-Meteo counts each location as one call and allows 600 calls per minute, so these limits keep one analysis inside that budget.
- **Same place.** An origin and destination that geocode within 0.5 mile of each other are treated as the same place.
- **Weather lookup points.** Weather is looked up at coordinates rounded to 2 decimals, which moves a point by at most about 0.4 mile.
- **Route labels.** Routes after the first are labelled "Alternative".

## Data providers and limitations

- **TomTom.**
  - The free tier has a monthly request quota per API. Geocoding results are cached for 1 hour and route responses for 10 minutes.
  - TomTom may return fewer alternative routes than requested, so the via-point fallback can add up to 4 extra routing requests.
  - Travel times come from the route's `progress` entries (cumulative distance and time), which is the most detailed timing TomTom provides.
  - A response section can report `travelMode: "other"` where truck restrictions could not be applied. This is logged on the server.
  - TomTom engine errors `NO_ROUTE_FOUND` and `MAP_MATCHING_FAILURE` are reported as `no_route_found`.
- **Open-Meteo.**
  - Free for non-commercial use, at 600 calls per minute, 5,000 per hour, and 10,000 per day per IP. Each location in a request counts as one call.
  - Coordinates are rounded to 2 decimals (about 0.7 mile) and deduplicated. Requests carry up to 100 locations each, and results are cached for 15 minutes.
  - Forecasts reach 16 days ahead.
  - A missing forecast value stays missing; it is never treated as 0.
  - The data is licensed under CC BY 4.0, which requires attribution.
- **Map tiles.** OpenFreeMap and OpenStreetMap contributors (attribution shown on the map).
- **Hosting.** The free Render service sleeps after 15 minutes idle, so the first request after that can take up to a minute.
