// MapLibre style expressions. Colours map backend risk values to display colours;
// nothing here decides a risk value.
import type { RiskLevel } from '../types/api'
import { hourKey } from './mapData'
import { MAP_COLORS } from './mapStyle'

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

// Heat layers are added in this order, so higher risk is drawn on top.
export const HEAT_LEVELS: readonly RiskLevel[] = [0, 1, 2, 3, 4]

export function heatLayerId(level: RiskLevel): string {
  return `corridor-heat-${level}`
}

/**
 * Corridor points whose backend risk for the hour equals the layer's level. A
 * missing (null) hour has no property, so it matches no layer and is never
 * drawn; 0 matches the Low layer.
 */
export function heatLevelFilter(hour: number, level: RiskLevel): Expression {
  return ['==', ['get', hourKey(hour)], level]
}

export const byRoute = (op: '==' | '!=', routeId: string): Expression => [op, ['get', 'routeId'], routeId]
export const byId = (op: '==' | '!=', routeId: string): Expression => [op, ['get', 'id'], routeId]
