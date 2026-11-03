import type { RouteStatus } from '../types/api'
import { STATUS_DISPLAY } from '../utils/format'

export function StatusBadge({ status }: { status: RouteStatus }) {
  const display = STATUS_DISPLAY[status]
  return <span className={`badge badge-${display.tone}`}>{display.label}</span>
}
