import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse } from '../test/fixtures'

vi.unmock('./places')
const { SUGGEST_TIMEOUT_MS, suggestPlaces } = await import('./places')

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('suggestPlaces', () => {
  it('asks the backend (never TomTom directly) with the encoded query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ suggestions: [{ label: 'Dallas, TX', type: 'area' }] }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await suggestPlaces('Dallas, T')).toEqual([{ label: 'Dallas, TX', type: 'area' }])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/places/suggest?q=Dallas%2C%20T')
    expect(String(fetchMock.mock.calls[0][0])).not.toMatch(/tomtom|key=/i)
  })

  it('rejects on an error status or an unexpected body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: { code: 'provider_error' } }, 502)))
    await expect(suggestPlaces('Dallas')).rejects.toThrow()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ suggestions: [{ label: 3 }] })))
    await expect(suggestPlaces('Dallas')).rejects.toThrow()
  })

  it('gives up after its timeout', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) =>
            init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))),
          ),
      ),
    )
    const pending = suggestPlaces('Dallas').catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(SUGGEST_TIMEOUT_MS)
    expect(await pending).toBeInstanceOf(DOMException)
  })
})
