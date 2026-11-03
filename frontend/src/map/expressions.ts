// MapLibre style expressions. Colours map backend risk values to display colours;
// nothing here decides a risk value.
import { hourKey } from './mapData'
import { HEAT_OPACITY, MAP_COLORS } from './mapStyle'

export type Expression = unknown[]

export const riskColor = (property: Expression): Expression => [
  'match',
  property,
  0,
  MAP_COLORS.risk[0],
  1,
  MAP_COLORS.risk[1],
  2,
  MAP_COLORS.risk[2],
  3,
  MAP_COLORS.risk[3],
  4,
  MAP_COLORS.risk[4],
  'rgba(0,0,0,0)',
]

/** Heatmap colour for one hour: the backend's risk value only, never point density. */
export function heatColor(hour: number): Expression {
  return riskColor(['get', hourKey(hour)])
}

/** Low stays subtle; higher risk is more opaque. */
export function heatOpacity(hour: number): Expression {
  const key = ['get', hourKey(hour)]
  return ['match', key, 0, HEAT_OPACITY[0], 1, HEAT_OPACITY[1], 2, HEAT_OPACITY[2], 3, HEAT_OPACITY[3], 4, HEAT_OPACITY[4], 0]
}

/** Only hours with data are drawn: a missing value (null) is never shown as Low. */
export function heatFilter(hour: number): Expression {
  return ['has', hourKey(hour)]
}

export const byRoute = (op: '==' | '!=', routeId: string): Expression => [op, ['get', 'routeId'], routeId]
export const byId = (op: '==' | '!=', routeId: string): Expression => [op, ['get', 'id'], routeId]
