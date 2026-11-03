import { useEffect, useState } from 'react'

// After this long, explain that a free server may be waking up.
export const SLOW_START_NOTICE_SECONDS = 10
// After this long, also explain that a busy provider (for example a weather
// rate-limit retry, which waits about 30 s) can add time.
export const BUSY_SERVICE_NOTICE_SECONDS = 30

interface AnalysisStatusProps {
  startedAt: number
}

/** A real waiting state: a spinner and the actual elapsed time. No estimated progress. */
export function AnalysisStatus({ startedAt }: AnalysisStatusProps) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  const elapsedSeconds = Math.max(0, Math.floor((now - startedAt) / 1000))

  return (
    <div className="analysis-status" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div>
        <p className="analysis-status-title">
          Analyzing routes and weather… <span className="elapsed">{elapsedSeconds} s</span>
        </p>
        <p className="analysis-status-detail">
          Comparing truck routes and checking the forecast at each checkpoint.
        </p>
        {elapsedSeconds >= SLOW_START_NOTICE_SECONDS && (
          <p className="analysis-status-detail">
            The server may be waking up after being idle. This can take up to a minute.
          </p>
        )}
        {elapsedSeconds >= BUSY_SERVICE_NOTICE_SECONDS && (
          <p className="analysis-status-detail">
            Still working. A busy weather or routing service can add up to a minute.
          </p>
        )}
      </div>
    </div>
  )
}
