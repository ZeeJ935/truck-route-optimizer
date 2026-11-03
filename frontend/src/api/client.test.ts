import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, makeResponse } from '../test/fixtures'
import type { AnalyzeRequest } from '../types/api'
import { ANALYZE_TIMEOUT_MS, ApiError, analyzeRoutes } from './client'

const REQUEST: AnalyzeRequest = {
  origin: 'Dallas, TX',
  destination: 'Denver, CO',
  departure_time: '2026-11-03T08:00:00+05:00',
  load_weight_lb: 40000,
  sampling_interval_miles: 25,
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('analyzeRoutes', () => {
  it('posts the request as JSON and returns the response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(makeResponse()))
    vi.stubGlobal('fetch', fetchMock)
    const result = await analyzeRoutes(REQUEST)
    expect(result.routes).toHaveLength(3)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/routes/analyze')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(REQUEST)
  })

  it('turns the backend error envelope into an ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: 'validation_error', message: 'Fix it', fields: { load_weight_lb: 'Too small' } } },
          400,
        ),
      ),
    )
    const error = await analyzeRoutes(REQUEST).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code: 'validation_error', message: 'Fix it', status: 400 })
    expect((error as ApiError).fields).toEqual({ load_weight_lb: 'Too small' })
  })

  it('reports a non-JSON failure as an unexpected response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 })))
    await expect(analyzeRoutes(REQUEST)).rejects.toMatchObject({ code: 'unexpected_response', status: 502 })
  })

  it('reports a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(analyzeRoutes(REQUEST)).rejects.toMatchObject({ code: 'network_error' })
  })

  it('waits two minutes, then reports a client timeout', async () => {
    expect(ANALYZE_TIMEOUT_MS).toBe(120_000)
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
          }),
      ),
    )
    const pending = analyzeRoutes(REQUEST).catch((caught: unknown) => caught)
    await vi.advanceTimersByTimeAsync(119_000)
    let settled = false
    void pending.then(() => {
      settled = true
    })
    await Promise.resolve()
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(1_000)
    expect(await pending).toMatchObject({ code: 'client_timeout' })
  })
})
