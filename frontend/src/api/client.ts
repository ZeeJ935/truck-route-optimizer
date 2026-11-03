import type { AnalysisResponse, AnalyzeRequest, ApiErrorBody } from '../types/api'

// Base URL of the Django API. Empty in local dev (Vite proxies /api).
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

// A long analysis takes 10-20 s, and a sleeping free server can need up to a
// minute to wake, so the client waits as long as the server's worker timeout.
export const ANALYZE_TIMEOUT_MS = 120_000

export class ApiError extends Error {
  readonly code: string
  readonly status: number | null
  readonly fields: Record<string, string>

  constructor(code: string, message: string, status: number | null = null, fields: Record<string, string> = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.fields = fields
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = (value as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

interface AnalyzeOptions {
  signal?: AbortSignal
  timeoutMs?: number
}

export async function analyzeRoutes(
  request: AnalyzeRequest,
  { signal, timeoutMs = ANALYZE_TIMEOUT_MS }: AnalyzeOptions = {},
): Promise<AnalysisResponse> {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const forwardAbort = () => controller.abort()
  signal?.addEventListener('abort', forwardAbort)

  try {
    const response = await fetch(`${API_BASE_URL}/api/routes/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
    const body: unknown = await response.json().catch(() => null)
    if (response.ok && body !== null) {
      return body as AnalysisResponse
    }
    if (isErrorBody(body)) {
      throw new ApiError(body.error.code, body.error.message, response.status, body.error.fields ?? {})
    }
    throw new ApiError(
      'unexpected_response',
      `The server returned an unexpected response (HTTP ${response.status}).`,
      response.status,
    )
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (timedOut) {
      throw new ApiError('client_timeout', 'The server did not respond within 2 minutes. Please try again.')
    }
    if (signal?.aborted) {
      throw new ApiError('aborted', 'The request was cancelled.')
    }
    throw new ApiError('network_error', 'Could not reach the server. Check your connection and try again.')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', forwardAbort)
  }
}
