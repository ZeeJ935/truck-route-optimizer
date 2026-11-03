# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest route based on weather, load weight, and travel time. It is built for the Spotter Full Stack Developer assessment. `SPEC.md` is the build specification.

> Status: Phase 0 (project skeleton and provider checks). The routing, weather, risk, and UI features are not implemented yet.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 6.1 + Django REST Framework (stateless, no database) |
| Frontend | React 19 + TypeScript + Vite |
| Routing and geocoding | TomTom Routing API (`travelMode=truck`) and Geocoding API, free tier |
| Weather | Open-Meteo forecast API (free, non-commercial) |
| Map (planned) | MapLibre GL JS with OpenFreeMap tiles |
| Hosting (planned) | Vercel Hobby (frontend), Render free web service (backend) |

## Repository layout

```text
backend/
  config/      Django settings and URLs
  api/         HTTP endpoints (currently GET /api/health)
  routing/     routing and geocoding providers (later phase)
  weather/     weather provider (later phase)
  risk/        RiskEngine (later phase)
  analysis/    analysis service (later phase)
  tests/       pytest suite
frontend/
  src/api/ components/ features/ map/ types/ utils/
```

## Local setup

Prerequisites: Python 3.13 or newer, and Node 20 or newer.

1. Copy `.env.example` to `.env` in the repo root and fill in `TOMTOM_API_KEY`. Set `DJANGO_DEBUG=true` for local development. Without it, `DJANGO_SECRET_KEY` is required.
2. Backend:

   ```bash
   cd backend
   python -m venv .venv
   .venv/Scripts/activate        # Windows; on macOS/Linux use: source .venv/bin/activate
   pip install -r requirements-dev.txt
   python manage.py runserver 127.0.0.1:8000
   pytest
   ```

3. Frontend, in a second terminal:

   ```bash
   cd frontend
   npm install
   npm run dev      # http://localhost:5173; /api is proxied to 127.0.0.1:8000
   npm run lint
   npm run build
   ```

## Environment variables

See `.env.example`. All provider keys stay server-side. The frontend only receives `VITE_API_BASE_URL`.

| Variable | Used by | Purpose |
|---|---|---|
| `TOMTOM_API_KEY` | backend | TomTom routing and geocoding |
| `DJANGO_SECRET_KEY` | backend | Required when `DJANGO_DEBUG` is not `true` |
| `DJANGO_DEBUG` | backend | `true` only for local development |
| `ALLOWED_HOSTS` | backend | Comma-separated host names |
| `CORS_ALLOWED_ORIGINS` | backend | Comma-separated frontend origins |
| `VITE_API_BASE_URL` | frontend | Backend base URL. Leave it empty locally |

## API

- `GET /api/health` returns `{"status": "ok"}`.
- `POST /api/routes/analyze` will be added in Phase 3.

## Assumptions

These are the places where the specification adds to or tightens the assessment brief:

- Ranking key: No Travel miles is ranked first, ahead of the brief's four criteria (Severe miles, High miles, average risk, travel time). Without it, a route with No Travel miles could beat a route with a small amount of Severe mileage.
- Continuous driving: checkpoint ETAs assume continuous driving at the provider's travel times, with no rest or fuel stops.
- Time zones: the departure is entered in the browser's time zone, and every trip time is shown in that same offset with a label, even when the route crosses time zones. All internal time logic uses UTC.
- Truck weight: the entered load (lb) is converted to kg and sent to TomTom as `vehicleWeight`. This is a lower bound on gross vehicle weight, because the truck's own weight is not known. The risk rules always use the entered load.
- Weather rates: Open-Meteo's `rain`, `showers`, and `snowfall` are sums over the preceding hour. They are used as the hourly rate (in/hr). Rain is `rain + showers`. Wind is the sustained 10 m wind speed, not gusts.
- Heatmap corridor: each final route is sampled every 25 miles, with a center point and one point 10 miles to each side. Density is reduced evenly above 600 points, and points shared between routes are deduplicated.

## Provider facts (checked in Phase 0)

These were checked on 2026-11-03.

- TomTom:
  - Truck routing and `vehicleWeight` (kg) work on the free key.
  - `maxAlternatives` accepts 0 to 5, but fewer routes may come back. A live Dallas to Denver request with `maxAlternatives=2` returned 2 routes, not 3.
  - `extendedRouteRepresentation=travelTime,distance` returns a `progress` array of per-point cumulative travel times. This is the most detailed timing available.
  - `sectionType=travelMode` reports any section where truck mode could not be applied, as `travelMode: "other"`.
  - The free tier has a monthly quota per API (about 20k routing and 20k geocoding requests) and requires no credit card.
- Open-Meteo:
  - The forecast covers 16 days.
  - Several locations can be sent in one request, as comma-separated coordinates (up to 1000).
  - Each location counts as at least one call against the free limits: 600 per minute, 5,000 per hour, and 10,000 per day. These limits apply per IP.
  - Use is non-commercial only, and the data is licensed CC BY 4.0, so attribution is required.
- Render free web service: it spins down after 15 minutes idle, and the first request after that can take about a minute.
