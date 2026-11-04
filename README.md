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
  gunicorn.conf.py  production server settings
frontend/
  src/
    api/         API client
    components/  UI components
    features/    feature modules (analysis state, form validation, forecast hours)
    map/         map, layers, legend
    types/       shared API types
    utils/       formatting and time helpers
  e2e/         Playwright checks and the labelled test fixture (not bundled)
render.yaml    Render Blueprint for the backend
frontend/vercel.json  Vercel settings for the frontend
```

## Getting started

Prerequisites: Python 3.14 or newer, and Node 20 or newer.

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

Backend variables go in `.env` in the repo root for local development (template: `.env.example`), and in the Render service settings in production. Frontend variables are set at build time (template: `frontend/.env.example`), and in the Vercel project settings in production.

| Variable | Used by | Required | Purpose |
|---|---|---|---|
| `TOMTOM_API_KEY` | backend | yes | TomTom routing and geocoding key. Stays on the server |
| `DJANGO_SECRET_KEY` | backend | in production | Required whenever `DJANGO_DEBUG` is not `true` |
| `DJANGO_DEBUG` | backend | no | `true` for local development only. Defaults to `false` |
| `ALLOWED_HOSTS` | backend | no | Comma-separated host names. Render's host name is added automatically from `RENDER_EXTERNAL_HOSTNAME` |
| `CORS_ALLOWED_ORIGINS` | backend | in production | Comma-separated frontend origins, e.g. `https://your-app.vercel.app` (no trailing slash) |
| `LOG_LEVEL` | backend | no | `DEBUG`, `INFO` (default), `WARNING` or `ERROR` |
| `SECURE_SSL_REDIRECT` | backend | no | Redirects HTTP to HTTPS. Defaults to `true` when `DJANGO_DEBUG` is `false` |
| `SECURE_HSTS_SECONDS` | backend | no | HSTS max-age. Defaults to 3600 |
| `CLIENT_IP_HEADER` | backend | no | Name of a request header that your host or proxy sets to the real client IP and that clients cannot override. Per-client rate limits use only this header. Leave it empty when no such header exists; see [Rate limits](#rate-limits) |
| `VITE_API_BASE_URL` | frontend | in production | Backend base URL, e.g. `https://your-api.onrender.com`. Leave empty locally, where Vite proxies `/api` |

- Local hosts and origins (`localhost`, the Vite dev server) are allowed only when `DJANGO_DEBUG` is `true`. Production never falls back to them.
- A production frontend build without `VITE_API_BASE_URL` shows a configuration error instead of calling its own host.
- Never commit `.env`. `VITE_` values are visible in the browser, so never put secrets in them.

## Tests and checks

```bash
# Backend
cd backend
pytest                # unit and API tests with fake providers; any network access fails the test
python manage.py check --deploy   # with production environment variables set

# Frontend
cd frontend
npm test              # Vitest + Testing Library; fetch and MapLibre are replaced by test doubles
npm run test:e2e      # Playwright browser checks against a labelled FIXTURE response (no backend needed)
npm run typecheck
npm run lint
npm run build         # type check + production build
```

There are three kinds of results, and they are kept separate:

- **Fake-provider tests** (backend `pytest`). TomTom, Open-Meteo and the clock are replaced by test doubles that live only in `backend/tests/`. They prove the rules exactly, including boundaries, all routes being unsafe, rate limits and provider failures. Production wiring cannot reach the fakes.
- **Fixture checks** (`npm run test:e2e` and a Vitest scenario). These replay `frontend/e2e/fixtures/FIXTURE-analysis-response.json`, which is synthetic and clearly labelled, to exercise the UI states in a real or test browser.
- **Live checks.** Real TomTom and Open-Meteo data through the running app. These depend on the current weather, so a scenario such as "every route is unsafe" can't be forced live.

## Deployment

The backend runs on a Render free web service, and the frontend on Vercel's free Hobby plan. Neither needs a payment method. If either service asks for a card, stop: this project is designed to use free plans only.

**Backend (Render)**
1. Create a web service from the GitHub repository, either from `render.yaml` (a Blueprint) or manually with these settings:
   - root directory `backend`
   - runtime Python, instance type Free
   - build command `pip install -r requirements.txt`
   - start command `gunicorn config.wsgi:application -c gunicorn.conf.py`
   - health check path `/api/health`
2. Set the environment variables:
   - `PYTHON_VERSION=3.14.8`
   - `DJANGO_DEBUG=false`
   - `DJANGO_SECRET_KEY` set to a long random value
   - `TOMTOM_API_KEY`
   - `CORS_ALLOWED_ORIGINS` set to the Vercel URL
   - `ALLOWED_HOSTS` is optional; Render's host name is added automatically

**Frontend (Vercel)**
1. Import the same repository with root directory `frontend`. The framework is Vite; `frontend/vercel.json` sets the build command, the output directory, an SPA rewrite and cache headers.
2. Set `VITE_API_BASE_URL` to the Render URL, then deploy.
3. Put the final Vercel URL into the backend's `CORS_ALLOWED_ORIGINS` and redeploy the backend.

**Gunicorn** (`backend/gunicorn.conf.py`)
- One worker with 4 threads, so the in-memory provider caches are shared and memory stays low.
- A 120-second worker timeout, because a long analysis takes 10–20 seconds and a sleeping free instance can need up to a minute to wake.
- Binds to `$PORT`.

**HTTPS** Render terminates TLS. Django trusts `X-Forwarded-Proto`, redirects HTTP to HTTPS (except the health check, which Render calls internally), and sends HSTS and `nosniff` headers.

**Cold starts** The free Render service sleeps after 15 minutes idle. The browser waits up to 120 seconds, shows the real elapsed time, and after 10 seconds explains that the server may be waking up.

**Server log** Each analysis logs one line with the time spent per stage (geocoding, routing, via attempts, weather, risk, ranking, serialization) and counts. The line never includes place names, URLs or keys.

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

Errors use one envelope on every API endpoint, including unknown paths and wrong methods: `{"error": {"code": "...", "message": "...", "fields": {...}}}`. `fields` appears only on validation errors.

| Code | HTTP | When |
|---|---|---|
| `validation_error` | 400 | Invalid input, malformed JSON, same origin and destination, or too many checkpoints for the weather budget |
| `geocoding_failed` | 422 | A place could not be found |
| `no_route_found` | 422 | No truck route exists between the places |
| `forecast_unavailable` | 422 | A checkpoint ETA on a final route has no eligible forecast hour |
| `not_found` | 404 | Unknown API path |
| `method_not_allowed` | 405 | Wrong HTTP method, for example `GET` on analyze |
| `request_too_large` | 413 | The request body is larger than 2.5 MB |
| `rate_limited` | 429 | Too many requests from one client. Includes `Retry-After`. See [Rate limits](#rate-limits) |
| `daily_limit_reached` | 503 | The app-wide daily weather cap is reached. Try again after midnight UTC |
| `provider_rate_limited` | 503 | A provider rate-limited the request. Includes `Retry-After: 60` |
| `provider_timeout` | 504 | A provider did not respond in time |
| `provider_error` | 502 | A provider failed or returned an unexpected response |
| `internal_error` | 500 | An unexpected server error. Details are logged on the server only |

Error messages never contain stack traces or raw provider responses.

### `GET /api/places/suggest?q=...`

Place suggestions for the Origin and Destination fields.
- `q` must be 3 to 100 characters.
- The response is `{"suggestions": [{"label": "Dallas, TX", "type": "area"}, ...]}`, where `type` is `address`, `street` or `area`. There are up to 5 suggestions, limited to the United States.
- Errors use the same envelope:
  - `validation_error` (400): the text is too short or too long
  - `provider_rate_limited` (503), `provider_timeout` (504), `provider_error` (502): TomTom failed
  - `rate_limited` (429): one client sent more than 60 requests a minute, which protects the free quota. The browser then simply shows no suggestions, and the user can keep typing the full address and run the analysis.

### Rate limits

Limits are checked before validation and before any TomTom or Open-Meteo call, so a refused request costs no provider quota.

| Limit | Scope | Error |
|---|---|---|
| Analyze: 6 a minute and 60 a day | per client | `rate_limited` (429) with `Retry-After` |
| Suggest: 60 a minute | per client | `rate_limited` (429) with `Retry-After` |
| 8,000 uncached weather locations a UTC day | whole app | `daily_limit_reached` (503) |

- **Client identity.** A client is identified only by the header named in `CLIENT_IP_HEADER`, which must be set by the host or proxy in a way clients cannot override. `X-Forwarded-For` is never used, because clients can add values to it. Local development (`DJANGO_DEBUG=true`) uses the socket address.
- **No trusted header.** If `CLIENT_IP_HEADER` is empty in production, per-client limits are switched off and the global daily cap is the protection.
- **Global weather cap.** Open-Meteo allows about 10,000 location calls a day per IP. Before any provider call, an analysis is refused if the worst case (550 locations) would pass 8,000 for the current UTC day. Only locations that are not already cached are counted, so a repeated trip within the cache time is free.
- **Counters are in memory.** Rate-limit and cap counters live in the server process. They reset when the server restarts or the free instance sleeps, so the cap is a safety net, not exact accounting.

## Risk rules

Each checkpoint's wind, rain, and snow are classified separately. The ranges are read as half-open, with inclusive lower bounds (see [Assumptions](#assumptions)).

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

## Address suggestions

The Origin and Destination fields suggest places as the driver types. This was added at the user's request, beyond the original brief.

- **Source.** The backend calls TomTom's Places Search "Suggest" API, using the same server-side `TOMTOM_API_KEY` as routing. No key reaches the browser, and no new environment variable is needed. TomTom's free tier allows 10,000 suggest requests a month, four times the 2,500 of the older fuzzy-search typeahead.
- **Requests.** A search starts only after 3 characters, about 300 ms after the last keystroke. A newer search cancels the outdated request. Repeat searches are answered from a cache in the browser for the session, and from a 1-hour cache on the server.
- **Results.** Up to 5 US addresses, streets, and cities or areas, shown as text such as "1600 Pennsylvania Avenue, Minneapolis, MN 55426". The country list is one constant, `PLACE_SUGGEST_COUNTRIES` in `backend/analysis/limits.py`.
- **Using it.** The fields are accessible comboboxes.
  - Keyboard: arrow keys move through the list, Enter chooses, Escape closes.
  - Mouse and touch: tap or click an option.
  - Screen readers hear how many suggestions are available.
- **Optional by design.** Choosing a suggestion only fills in the text, and the analysis geocodes that text as before. If suggestions fail or are slow, the list simply doesn't appear, and the driver can still type any address and run the analysis.

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
  - The selected route is the strongest: a thick blue line with a white casing, always drawn above the other routes, so it stays visible on shared highways.
  - The top-ranked route, when not selected, is a dashed green line, labelled with its backend label ("Recommended", or "Best available, not safe").
  - The other routes are muted grey.
- **Risk sections on the road.** Each High, Severe or No Travel checkpoint colours the road it represents: from the midpoint with the previous checkpoint to the midpoint with the next one, the same rule the backend uses for mileage. High is orange, Severe is red and No Travel is purple. Neighbouring sections of the same level are merged.
  - Sections and checkpoints are drawn for **every** route.
  - The selected route's are full strength, with a dark outline, and sit on top.
  - Other routes' are thinner and semi-transparent, so the map stays readable.
- **Checkpoints.** Dots coloured by risk. They're smaller at overview zoom, and High or worse stay larger. Hovering a dot shows its ETA and forecast hour with the time-zone label, mile, wind, rain, snow, risk and reasons. Clicking pins the popup.
- **Route summaries.** Hovering any route line shows its rank, label, status, distance, travel time, No Travel, Severe and High miles, and average risk. Clicking a route selects it and pins its summary.
- **Markers.** "A" marks the origin and "B" the destination.
- **Legend.** It describes every colour in text: routes, road sections, checkpoints, and the heatmap. It is collapsible and starts collapsed on narrow screens.
- **Selection.** Clicking a route on the map selects it in the panel, and selecting a card in the panel highlights the route on the map. Switching only changes layer filters: no data is rebuilt, no request is made, and the view doesn't move.
- **Fitting.** After each analysis, the view fits all routes, keeping them clear of the slider panel and the legend.
- **Performance.** Measured on the largest response (Dallas to Denver at 10-mile sampling, about 32,000 route points), with no geometry simplification:
  - route switches took 36–54 ms
  - panning and zooming produced no main-thread long tasks

  The drawn lines therefore use the full route geometry.
- **Loading.** MapLibre loads as a separate chunk after the form and results, and its web worker is served as its own asset.

## Corridor heatmap and forecast slider

There are two time views, and both are labelled in the app:
- **Checkpoints** show the weather at each checkpoint's ETA.
- **The heatmap** shows the whole trip corridor at the time selected on the slider.

**The slider**
- It has 49 positions. Hour N is departure + N hours, and hour 0 is the departure. The label shows the date and time in the trip's UTC offset, for example "+12 h · Nov 4, 14:10 UTC+05:00".
- It's a native range input, so it works with mouse, touch and keyboard: arrow keys step one hour, and Home and End jump to the first and last available hours.
- Hours with no data (from the backend's `forecast.available_hours`) can't be selected. Moving onto one skips to the nearest available hour in the direction of movement. Those hours are hatched grey in the strip under the slider, and the backend's notice explains why.
- Moving the slider makes no network request. Each move only updates the filters of the five heat layers; the heatmap data is built once per analysis and never rebuilt, and no paint property changes.

**The heatmap**
- **Colour comes only from the backend's risk value for the selected hour, never from point density.** Each corridor point is a soft blurred circle coloured by that value, so overlapping Low points stay Low.
- **The highest risk stays on top.** There is one map layer per risk level, stacked from Low at the bottom to No Travel at the top. Each layer has a fixed colour and shows only the points at its level for the selected hour. Severe and No Travel cells are therefore always drawn over nearby Low circles. They also have firmer edges and higher opacity than Low, so they stay visible next to the route line.
- **Missing data isn't drawn.** Corridor values are stored as one property per hour (`h0` … `h48`). An hour with no forecast has no property, so it matches no layer and is never shown as Low. 0 is a valid Low value.
- **Low is subtle.** Low is the most transparent level and the risk levels get more opaque as they rise, so the routes and basemap stay readable.
- **Circle size scales with zoom** (about a 20-mile radius), so points 25 miles apart along the route merge into one continuous band.
- **Data format.** MapLibre 6 was also checked in the browser with an array property and an `at` expression, which works. The flat per-hour format was kept because missing hours are simpler and unambiguous that way.

## Test fixture

`frontend/e2e/fixtures/FIXTURE-analysis-response.json` is synthetic, clearly labelled test data. It is not a real route, forecast or backend result. It covers:
- High, Severe and No Travel checkpoints
- every route having No Travel miles, so the global warning shows
- forecast hours 36–48 missing

Two checks use it, and their screenshots and results are fixture results, not live ones:
- the Playwright checks in `frontend/e2e/`, which intercept the analyze request
- a Vitest scenario test

The fixture lives outside `src/`, so it never enters the production bundle.

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
- **Threshold boundaries.** The brief writes ranges as whole numbers (25–34 mph) or with shared edges (rain 0.10–0.25 and 0.25–0.50 in/hr). They are read as half-open ranges with an inclusive lower bound: 34.9 mph is Moderate and 35 mph is High. A value on a shared edge counts as the higher level, so 0.25 in/hr of rain is High and 0.50 in/hr is Severe; the same applies to snow at 1.0 and 2.0 in/hr. The top of Severe is inclusive (rain 1.00 and snow 3.0 are Severe), matching the brief's "> 1.00" and "> 3.0" for No Travel.
- **Displayed segment miles.** Each checkpoint's `segment_miles` is rounded to 0.1 mile for display. Scoring uses the unrounded values, so the shown segments can add up to slightly more or less than the route length (two 16.05-mile segments show as 16.1 each on a 32.1-mile route).

## Data providers

- **TomTom Routing and Geocoding (free tier).**
  - Truck mode with the load sent as `vehicleWeight`.
  - Travel times come from the route's `progress` entries (cumulative distance and time), which is the most detailed timing TomTom provides.
  - Geocoding results are cached for 1 hour and route responses for 10 minutes.
  - A section reported as `travelMode: "other"` (truck restrictions not applied) is logged on the server.
  - The engine errors `NO_ROUTE_FOUND` and `MAP_MATCHING_FAILURE` are reported as `no_route_found`.
- **TomTom Places Search Suggest (free tier).** Place suggestions for the Origin and Destination fields: 10,000 free requests a month, no card. It uses the same key as routing.
- **Open-Meteo forecast API (free, non-commercial).**
  - Hourly wind, rain, showers and snowfall in mph and inches, in UTC, up to 16 days ahead.
  - Coordinates are rounded to 2 decimals and deduplicated, sent in batches of up to 100, and cached for 15 minutes.
  - A missing value stays missing; it is never treated as 0.
  - The data is licensed under CC BY 4.0, and attribution is shown on the map.
- **Map tiles.** OpenFreeMap with OpenMapTiles and OpenStreetMap data (attribution shown on the map).

## Known limitations

- **Free hosting cold start.** The Render free service sleeps after 15 minutes idle, so the first request afterwards can take up to a minute.
- **Weather rate limits.** Open-Meteo's free limit is 600 calls per minute per IP, and each location counts as one call. Render's outbound IPs can be shared with other services. Two long analyses in a row may wait about 30 seconds for one retry, or fail with `provider_rate_limited`. The free API is for non-commercial use only.
- **Routing quota and alternatives.**
  - TomTom's free tier has a monthly request quota.
  - TomTom often returns fewer than 3 alternatives. The via-point fallback is a heuristic and may still find fewer than 3 distinct routes within 1.5 times the fastest time; the app then says so.
- **Very long trips.**
  - At a 10-mile interval, more than 450 distinct checkpoint locations exceed the weather budget, and the app asks for a larger interval.
  - A checkpoint ETA beyond the 16-day forecast horizon fails with `forecast_unavailable`.
- **ETA model.**
  - ETAs assume continuous driving at TomTom's travel times, with no rest breaks, fuel stops or hours-of-service rules.
  - Traffic is TomTom's prediction for the departure time.
- **Weather model.**
  - Forecasts are hourly model data at roughly 1–2 km resolution, looked up at points rounded to about 0.4 mile.
  - Precipitation is the total for the preceding hour, used as the hourly rate.
  - Wind is the sustained 10 m wind, not gusts.
- **Truck profile.** Only the load weight is sent, as a lower bound on gross vehicle weight. Truck dimensions, axle weights and hazardous materials are not modelled.
- **Address suggestions.** Suggestions cover the United States only (one constant to change). Each pause in typing that isn't already cached uses one of the 10,000 free monthly TomTom suggest requests. Requests are limited to 60 a minute per client when a trusted client-IP header is configured.
- **Rate limits.** Per-client limits need a trusted client-IP header from the host (`CLIENT_IP_HEADER`). Without one, only the app-wide daily weather cap applies. All counters are in memory and reset when the server restarts.
- **Geocoding.** The top geocoding result is used. An ambiguous name may resolve to an unexpected place, which the app shows in the results.
- **Heatmap coverage.** The corridor is sampled every 25 miles, with points 10 miles to each side, and is capped at 250 points. It shows weather along the routes, not the whole region.
- **Time display.** All trip times use the departure's UTC offset, even when the route crosses time zones; the offset is always labelled.
- **Caches.** Caches are in memory per server process, so they are lost on restart or when the free instance sleeps.
- **Python version.** The code is tested locally on Python 3.15 and deployed on Python 3.14.8.
- **Performance figures.** Frame timings in this project were measured in headless Chromium, so they are relative indicators, not real-device frame rates.
