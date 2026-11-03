import { AnalysisForm } from './components/AnalysisForm'
import { AnalysisStatus } from './components/AnalysisStatus'
import { CheckpointList } from './components/CheckpointList'
import { ErrorBanner } from './components/ErrorBanner'
import { GlobalWarning, RouteNotice } from './components/Notices'
import { RecommendationPanel } from './components/RecommendationPanel'
import { RouteList } from './components/RouteList'
import { useAnalysis } from './features/analysis/useAnalysis'
import { toAnalyzeRequest, type FormValues } from './features/analysis/validateForm'
import './App.css'

function App() {
  const { state, submit, selectedRouteId, selectRoute } = useAnalysis()

  const serverErrors = state.status === 'error' ? state.error.fields : {}
  const handleSubmit = (values: FormValues) => {
    void submit(toAnalyzeRequest(values))
  }

  const result = state.status === 'success' ? state.data : null
  const recommended = result?.routes.find((route) => route.id === result.recommendation.route_id)
  const selected = result?.routes.find((route) => route.id === selectedRouteId) ?? recommended

  return (
    <div className="app">
      <header className="app-header">
        <h1>Weather-Aware Truck Routing</h1>
      </header>
      <div className="app-body">
        <aside className="side-panel">
          <AnalysisForm busy={state.status === 'loading'} serverErrors={serverErrors} onSubmit={handleSubmit} />

          {state.status === 'loading' && <AnalysisStatus startedAt={state.startedAt} />}
          {state.status === 'error' && <ErrorBanner error={state.error} />}

          {state.status === 'success' && result && recommended && selected && (
            <div className="results">
              {result.recommendation.no_safe_route && <GlobalWarning />}
              <RecommendationPanel recommendation={result.recommendation} route={recommended} />
              {result.route_notice && <RouteNotice notice={result.route_notice} />}
              <RouteList routes={result.routes} selectedId={selected.id} onSelect={selectRoute} />
              <CheckpointList route={selected} tripOffsetMinutes={state.tripOffsetMinutes} />
            </div>
          )}
        </aside>

        <main className="workspace" aria-label="Map workspace">
          <div className="workspace-empty">
            {selected ? (
              <p>
                Selected: <strong>Route {selected.rank}</strong> ({selected.label})
              </p>
            ) : (
              <p>Enter a trip to compare truck routes by weather risk.</p>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
