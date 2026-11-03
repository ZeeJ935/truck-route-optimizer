import { lazy, Suspense, useState } from 'react'
import { AnalysisForm } from './components/AnalysisForm'
import { AnalysisStatus } from './components/AnalysisStatus'
import { CheckpointList } from './components/CheckpointList'
import { ErrorBanner } from './components/ErrorBanner'
import { ForecastSlider } from './components/ForecastSlider'
import { GlobalWarning, RouteNotice } from './components/Notices'
import { RecommendationPanel } from './components/RecommendationPanel'
import { RouteList } from './components/RouteList'
import { useAnalysis } from './features/analysis/useAnalysis'
import { toAnalyzeRequest, type FormValues } from './features/analysis/validateForm'
import { firstAvailableHour } from './features/forecast/hours'
import { MapLegend } from './map/MapLegend'
import type { AnalysisResponse, CorridorPoint, RouteResult } from './types/api'
import './App.css'

const NO_ROUTES: RouteResult[] = []
const NO_CORRIDOR: CorridorPoint[] = []

// MapLibre is large; load the map separately so the form and results appear first.
const RouteMap = lazy(() => import('./map/RouteMap').then((module) => ({ default: module.RouteMap })))

function App() {
  const { state, submit, clearError, selectedRouteId, selectRoute } = useAnalysis()
  // The slider hour belongs to one analysis result; a new result starts at its first available hour.
  const [hourChoice, setHourChoice] = useState<{ data: AnalysisResponse | null; hour: number }>({
    data: null,
    hour: 0,
  })

  const serverErrors = state.status === 'error' ? state.error.fields : {}
  const handleSubmit = (values: FormValues) => {
    void submit(toAnalyzeRequest(values))
  }

  const result = state.status === 'success' ? state.data : null
  const tripOffsetMinutes = state.status === 'success' ? state.tripOffsetMinutes : 0
  const recommended = result?.routes.find((route) => route.id === result.recommendation.route_id)
  const selected = result?.routes.find((route) => route.id === selectedRouteId) ?? recommended
  const selectedHour =
    result && hourChoice.data === result ? hourChoice.hour : firstAvailableHour(result?.forecast.available_hours ?? [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Weather-Aware Truck Routing</h1>
      </header>
      <div className="app-body">
        <aside className="side-panel">
          <AnalysisForm
            busy={state.status === 'loading'}
            serverErrors={serverErrors}
            onSubmit={handleSubmit}
            onEdit={clearError}
          />

          {state.status === 'loading' && <AnalysisStatus startedAt={state.startedAt} />}
          {state.status === 'error' && <ErrorBanner error={state.error} />}

          {state.status === 'success' && result && recommended && selected && (
            <div className="results">
              {result.recommendation.no_safe_route && <GlobalWarning />}
              <RecommendationPanel recommendation={result.recommendation} route={recommended} />
              {result.route_notice && <RouteNotice notice={result.route_notice} />}
              <RouteList routes={result.routes} selectedId={selected.id} onSelect={selectRoute} />
              <CheckpointList route={selected} tripOffsetMinutes={tripOffsetMinutes} />
            </div>
          )}
        </aside>

        <main className="workspace" aria-label="Map workspace">
          <Suspense fallback={null}>
            <RouteMap
              routes={result?.routes ?? NO_ROUTES}
              corridor={result?.forecast.corridor ?? NO_CORRIDOR}
              selectedHour={selectedHour}
              selectedRouteId={selected?.id ?? null}
              recommendedRouteId={result?.recommendation.route_id ?? null}
              tripOffsetMinutes={tripOffsetMinutes}
              onSelectRoute={selectRoute}
            />
          </Suspense>
          {result && recommended ? (
            <>
              <MapLegend topRouteLabel={recommended.label} />
              <ForecastSlider
                forecast={result.forecast}
                hour={selectedHour}
                tripOffsetMinutes={tripOffsetMinutes}
                onHourChange={(hour) => setHourChoice({ data: result, hour })}
              />
            </>
          ) : (
            <p className="map-hint">Enter a trip to compare truck routes by weather risk.</p>
          )}
        </main>
      </div>
    </div>
  )
}

export default App
