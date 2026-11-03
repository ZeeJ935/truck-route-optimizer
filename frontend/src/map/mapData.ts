// Display helpers for the map. They reshape backend results into map features;
// they make no risk, ranking, or status decisions.
import type { Checkpoint, RiskLevel, RouteResult } from '../types/api'
import { formatTripTime } from '../utils/time'

export type LngLat = [number, number]

export interface LineFeature<P> {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: LngLat[] }
  properties: P
}

export interface PointFeature<P> {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: LngLat }
  properties: P
}

export interface FeatureCollection<F> {
  type: 'FeatureCollection'
  features: F[]
}

export interface RouteProps {
  id: string
  rank: number
  recommended: boolean
}

export interface HazardProps {
  level: RiskLevel
  fromMile: number
  toMile: number
}

export interface CheckpointProps {
  index: number
  risk: RiskLevel
  mile: number
}

// Severe and No Travel sections are drawn over the selected route.
export const HAZARD_MIN_RISK: RiskLevel = 3

const EARTH_RADIUS_MILES = 3958.7613

function haversineMiles(a: LngLat, b: LngLat): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(b[1] - a[1])
  const dLng = toRad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_MILES * Math.asin(Math.min(1, Math.sqrt(h)))
}

/**
 * Distance along the drawn line at each vertex, scaled so it ends at the route's
 * reported length (the same distance basis the backend uses for checkpoint miles).
 */
export function cumulativeMiles(geometry: LngLat[], routeMiles: number): number[] {
  const totals = [0]
  for (let i = 1; i < geometry.length; i++) totals.push(totals[i - 1] + haversineMiles(geometry[i - 1], geometry[i]))
  const measured = totals[totals.length - 1]
  if (measured <= 0) return totals
  const scale = routeMiles / measured
  return totals.map((value) => value * scale)
}

function pointAt(geometry: LngLat[], cumulative: number[], mile: number): LngLat {
  if (mile <= 0) return geometry[0]
  const last = cumulative.length - 1
  if (mile >= cumulative[last]) return geometry[last]
  let low = 0
  let high = last
  while (high - low > 1) {
    const mid = (low + high) >> 1
    if (cumulative[mid] < mile) low = mid
    else high = mid
  }
  const span = cumulative[high] - cumulative[low]
  const t = span === 0 ? 0 : (mile - cumulative[low]) / span
  return [
    geometry[low][0] + (geometry[high][0] - geometry[low][0]) * t,
    geometry[low][1] + (geometry[high][1] - geometry[low][1]) * t,
  ]
}

/** The part of the line between two miles, interpolating the ends. */
export function sliceLine(geometry: LngLat[], cumulative: number[], fromMile: number, toMile: number): LngLat[] {
  const coords: LngLat[] = [pointAt(geometry, cumulative, fromMile)]
  for (let i = 0; i < geometry.length; i++) {
    if (cumulative[i] > fromMile && cumulative[i] < toMile) coords.push(geometry[i])
  }
  coords.push(pointAt(geometry, cumulative, toMile))
  return coords
}

/**
 * Mile range each checkpoint represents: from the midpoint with the previous
 * checkpoint to the midpoint with the next one (first and last run to the ends).
 */
export function representedRanges(checkpoints: Checkpoint[], routeMiles: number): [number, number][] {
  return checkpoints.map((checkpoint, i) => {
    const from = i === 0 ? 0 : (checkpoints[i - 1].mile + checkpoint.mile) / 2
    const to = i === checkpoints.length - 1 ? routeMiles : (checkpoint.mile + checkpoints[i + 1].mile) / 2
    return [from, to]
  })
}

/** Severe and No Travel sections of a route, with neighbouring sections of the same level merged. */
export function hazardSections(route: RouteResult, cumulative?: number[]): FeatureCollection<LineFeature<HazardProps>> {
  const totals = cumulative ?? cumulativeMiles(route.geometry, route.distance_miles)
  const ranges = representedRanges(route.checkpoints, route.distance_miles)
  const merged: HazardProps[] = []
  route.checkpoints.forEach((checkpoint, i) => {
    if (checkpoint.risk < HAZARD_MIN_RISK) return
    const [from, to] = ranges[i]
    const previous = merged[merged.length - 1]
    if (previous && previous.level === checkpoint.risk && previous.toMile === from) previous.toMile = to
    else merged.push({ level: checkpoint.risk, fromMile: from, toMile: to })
  })
  return {
    type: 'FeatureCollection',
    features: merged.map((section) => ({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: sliceLine(route.geometry, totals, section.fromMile, section.toMile),
      },
      properties: section,
    })),
  }
}

export function routeFeatures(
  routes: RouteResult[],
  recommendedId: string,
  geometryFor: (route: RouteResult) => LngLat[] = (route) => route.geometry,
): FeatureCollection<LineFeature<RouteProps>> {
  return {
    type: 'FeatureCollection',
    features: routes.map((route) => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: geometryFor(route) },
      properties: { id: route.id, rank: route.rank, recommended: route.id === recommendedId },
    })),
  }
}

export function checkpointFeatures(route: RouteResult): FeatureCollection<PointFeature<CheckpointProps>> {
  return {
    type: 'FeatureCollection',
    features: route.checkpoints.map((checkpoint, index) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [checkpoint.lng, checkpoint.lat] },
      properties: { index, risk: checkpoint.risk, mile: checkpoint.mile },
    })),
  }
}

export interface CheckpointPopup {
  title: string
  risk: string
  lines: string[]
  reasons: string[]
}

/** Text for a checkpoint popup. Every value comes from the backend. */
export function checkpointPopup(route: RouteResult, checkpoint: Checkpoint, offsetMinutes: number): CheckpointPopup {
  return {
    title: `Route ${route.rank} · Mile ${checkpoint.mile.toFixed(1)}`,
    risk: checkpoint.risk_label,
    lines: [
      `ETA ${formatTripTime(checkpoint.eta, offsetMinutes)}`,
      `Forecast hour ${formatTripTime(checkpoint.weather.forecast_time, offsetMinutes)}`,
      `Wind ${checkpoint.weather.wind_mph} mph`,
      `Rain ${checkpoint.weather.rain_in_per_hour} in/hr`,
      `Snow ${checkpoint.weather.snow_in_per_hour} in/hr`,
    ],
    reasons: checkpoint.reasons,
  }
}

/** [[west, south], [east, north]] around every route. */
export function routesBounds(routes: RouteResult[]): [LngLat, LngLat] | null {
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  for (const route of routes) {
    for (const [lng, lat] of route.geometry) {
      if (lng < west) west = lng
      if (lng > east) east = lng
      if (lat < south) south = lat
      if (lat > north) north = lat
    }
  }
  return Number.isFinite(west) ? [[west, south], [east, north]] : null
}
