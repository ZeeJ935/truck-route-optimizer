import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, analyzeRoutes } from '../../api/client'
import type { AnalysisResponse, AnalyzeRequest } from '../../types/api'
import { offsetFromIso } from '../../utils/time'

export type AnalysisState =
  | { status: 'idle' }
  | { status: 'loading'; startedAt: number }
  | { status: 'success'; data: AnalysisResponse; tripOffsetMinutes: number }
  | { status: 'error'; error: ApiError }

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({ status: 'idle' })
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => controllerRef.current?.abort(), [])

  const submit = useCallback(async (request: AnalyzeRequest) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState({ status: 'loading', startedAt: Date.now() })
    try {
      const data = await analyzeRoutes(request, { signal: controller.signal })
      if (controller.signal.aborted) return
      setSelectedRouteId(data.recommendation.route_id)
      setState({ status: 'success', data, tripOffsetMinutes: offsetFromIso(request.departure_time) })
    } catch (error) {
      if (controller.signal.aborted) return
      const apiError =
        error instanceof ApiError ? error : new ApiError('unexpected_error', 'Something went wrong. Please try again.')
      setState({ status: 'error', error: apiError })
    }
  }, [])

  return { state, submit, selectedRouteId, selectRoute: setSelectedRouteId }
}
