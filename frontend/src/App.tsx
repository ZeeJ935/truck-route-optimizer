import { useEffect, useState } from 'react'
import { fetchHealth } from './api/client'

type HealthState = 'checking' | 'ok' | 'error'

function App() {
  const [health, setHealth] = useState<HealthState>('checking')

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((result) => setHealth(result.status === 'ok' ? 'ok' : 'error'))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error(error)
          setHealth('error')
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Weather-Aware Truck Routing</h1>
      <p data-testid="backend-health">Backend: {health}</p>
    </main>
  )
}

export default App
