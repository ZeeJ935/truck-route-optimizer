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
  analysis/    checkpoints, ETAs, forecast matching, scoring, limits
  risk/        risk levels, thresholds, RiskEngine
  routing/     routing and geocoding providers
  weather/     weather provider
  tests/       pytest suite (network blocked)
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
npm run lint
npm run build         # type check + production build
```

## API

### `GET /api/health`

Returns the service status.

```json
{ "status": "ok" }
```

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

## Assumptions

- **No Travel miles come first in the ranking.** The brief lists Severe miles, High miles, average risk, and travel time. No Travel miles are added in front of these; otherwise a route with No Travel miles could beat a route with a small amount of Severe mileage.
- **Continuous driving.** ETAs assume continuous driving at the provider's travel times, with no rest or fuel stops.
- **Time zones.** The departure is read in the browser's time zone and sent with its UTC offset. Every trip time is shown in that same offset, with a label, even when the route crosses time zones. The backend works in UTC.
- **Vehicle weight.** The entered load is converted from lb to kg and sent to TomTom as `vehicleWeight`. This is a lower bound on gross vehicle weight, because the truck's own weight is unknown. The risk rules always use the entered load.
- **Weather values.** Open-Meteo's `rain`, `showers`, and `snowfall` are totals for the preceding hour. They are used as the hourly rate. Rain is `rain + showers`, and wind is the sustained 10 m wind speed, not gusts.
- **Heatmap corridor.** Each route is sampled every 25 miles, with one centre point and one point 10 miles to each side. Points shared between routes are deduplicated.
- **Weather location limits.** The corridor is capped at 250 points, and one analysis requests at most 550 distinct weather locations (`backend/analysis/limits.py`). Open-Meteo counts each location as one call and allows 600 calls per minute, so these limits keep one analysis inside that budget.
- **Route labels.** Routes after the first are labelled "Alternative".

## Data providers and limitations

- **TomTom.**
  - The free tier has a monthly request quota per API.
  - TomTom may return fewer alternative routes than requested.
  - A response section can report `travelMode: "other"` where truck restrictions could not be applied.
- **Open-Meteo.**
  - Free for non-commercial use, at 600 calls per minute, 5,000 per hour, and 10,000 per day per IP. Each location in a request counts as one call.
  - Forecasts reach 16 days ahead.
  - The data is licensed under CC BY 4.0, which requires attribution.
- **Map tiles.** OpenFreeMap and OpenStreetMap contributors (attribution shown on the map).
- **Hosting.** The free Render service sleeps after 15 minutes idle, so the first request after that can take up to a minute.
