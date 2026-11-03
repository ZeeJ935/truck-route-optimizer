import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
  type GeoJSONSource,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CorridorPoint, RouteResult } from '../types/api'
import {
  allCheckpointFeatures,
  allHazardSections,
  checkpointPopup,
  cumulativeMiles,
  heatmapFeatures,
  routeFeatures,
  routeSummaryPopup,
  routesBounds,
  type CheckpointProps,
} from './mapData'
import { HEAT_LEVELS, byId, byRoute, heatLayerId, heatLevelFilter, riskColor } from './expressions'
import { HEAT_BLUR, HEAT_OPACITY, MAP_COLORS, MAP_STYLE_URL, WEATHER_ATTRIBUTION } from './mapStyle'

// MapLibre 6 looks for its worker next to its own module file. Vite pre-bundles
// and hashes that file, so point MapLibre at the worker asset Vite emits instead.
setWorkerUrl(maplibreWorkerUrl)

const EMPTY = { type: 'FeatureCollection' as const, features: [] }
const NONE = '__none__'
const INITIAL_VIEW = { center: [-98.5, 39.5] as [number, number], zoom: 3.3 }

interface RouteMapProps {
  routes: RouteResult[]
  corridor: CorridorPoint[]
  selectedHour: number
  selectedRouteId: string | null
  recommendedRouteId: string | null
  tripOffsetMinutes: number
  onSelectRoute: (routeId: string) => void
}

function setData(map: MapLibreMap, sourceId: string, data: unknown) {
  ;(map.getSource(sourceId) as GeoJSONSource | undefined)?.setData(data as Parameters<GeoJSONSource['setData']>[0])
}

function addLayers(map: MapLibreMap, hour: number) {
  map.addSource('corridor', { type: 'geojson', data: EMPTY })
  map.addSource('routes', { type: 'geojson', data: EMPTY })
  map.addSource('hazards', { type: 'geojson', data: EMPTY })
  map.addSource('checkpoints', { type: 'geojson', data: EMPTY })
  const add = (layer: Record<string, unknown>) => map.addLayer(layer as never)
  const lineLayout = { 'line-join': 'round', 'line-cap': 'round' }

  // Corridor heatmap: one layer per risk level, stacked Low (bottom) to No Travel
  // (top), so a higher risk is always drawn over nearby lower-risk circles. Each
  // layer has a fixed colour; its filter selects the points at that level for the
  // selected hour. Soft circles grow with zoom so neighbouring points (25 miles
  // apart, plus 10 miles to each side) merge into one continuous band.
  for (const level of HEAT_LEVELS) {
    add({
      id: heatLayerId(level),
      type: 'circle',
      source: 'corridor',
      filter: heatLevelFilter(hour, level),
      paint: {
        'circle-color': MAP_COLORS.risk[level],
        'circle-opacity': HEAT_OPACITY[level],
        'circle-blur': HEAT_BLUR[level],
        // About a 20-mile radius at mid latitudes (pixels per mile double each zoom level).
        'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 0, 0.52, 12, 2150],
      },
    })
  }

  // Other routes and their overlays: muted, underneath the selected route.
  add({ id: 'routes-other-casing', type: 'line', source: 'routes', layout: lineLayout,
    paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.8 }, filter: byId('!=', NONE) })
  add({ id: 'routes-other', type: 'line', source: 'routes', layout: lineLayout,
    paint: { 'line-color': MAP_COLORS.otherRoute, 'line-width': 4, 'line-opacity': 0.6 }, filter: byId('!=', NONE) })
  add({ id: 'hazard-other', type: 'line', source: 'hazards', layout: lineLayout,
    paint: { 'line-color': riskColor(['get', 'level']), 'line-width': 5, 'line-opacity': 0.55 }, filter: byRoute('!=', NONE) })
  add({ id: 'checkpoints-other', type: 'circle', source: 'checkpoints',
    paint: {
      'circle-color': riskColor(['get', 'risk']),
      'circle-opacity': 0.6,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, ['step', ['get', 'risk'], 1.5, 2, 3], 10, ['step', ['get', 'risk'], 4, 2, 6]],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1,
      'circle-stroke-opacity': 0.6,
    },
    filter: byRoute('!=', NONE) })

  // The top-ranked route, when another route is selected: dashed green.
  add({ id: 'route-recommended', type: 'line', source: 'routes', layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: { 'line-color': MAP_COLORS.recommended, 'line-width': 4, 'line-dasharray': [2, 1.5] }, filter: byId('==', NONE) })

  // The selected route and its overlays: strongest, always on top.
  add({ id: 'route-selected-casing', type: 'line', source: 'routes', layout: lineLayout,
    paint: { 'line-color': '#ffffff', 'line-width': 11 }, filter: byId('==', NONE) })
  add({ id: 'route-selected', type: 'line', source: 'routes', layout: lineLayout,
    paint: { 'line-color': MAP_COLORS.selected, 'line-width': 6 }, filter: byId('==', NONE) })
  add({ id: 'hazard-selected-casing', type: 'line', source: 'hazards', layout: lineLayout,
    paint: { 'line-color': MAP_COLORS.hazardCasing, 'line-width': 12 }, filter: byRoute('==', NONE) })
  add({ id: 'hazard-selected', type: 'line', source: 'hazards', layout: lineLayout,
    paint: { 'line-color': riskColor(['get', 'level']), 'line-width': 8 }, filter: byRoute('==', NONE) })

  // Wide invisible lines that make every route easy to hover and click.
  add({ id: 'routes-hit', type: 'line', source: 'routes', layout: lineLayout,
    paint: { 'line-color': '#000000', 'line-width': 18, 'line-opacity': 0 } })

  // Checkpoints of the selected route, coloured by risk.
  add({ id: 'checkpoints-selected', type: 'circle', source: 'checkpoints',
    paint: {
      // Small at overview zoom so the selected line stays visible at 10-mile spacing;
      // High and above stay larger at every zoom.
      'circle-radius': ['interpolate', ['linear'], ['zoom'],
        4, ['step', ['get', 'risk'], 2.5, 2, 5],
        8, ['step', ['get', 'risk'], 5, 2, 7],
        11, ['step', ['get', 'risk'], 7, 2, 9]],
      'circle-color': riskColor(['get', 'risk']),
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 1, 8, 2],
    },
    filter: byRoute('==', NONE) })
}

const CHECKPOINT_LAYERS = ['checkpoints-selected', 'checkpoints-other']

/** Keep fitted routes clear of the slider panel (bottom) and the open legend (top-left on wide screens). */
function fitPadding(container: HTMLElement | null) {
  const width = container?.clientWidth ?? 0
  const height = container?.clientHeight ?? 0
  const wide = width > 800
  return {
    top: 40,
    right: 48,
    bottom: Math.min(210, Math.max(40, Math.round(height * 0.3))),
    left: wide ? 260 : 40,
  }
}

function element(tag: string, className: string, text?: string): HTMLElement {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

function endpointMarker(label: string, title: string): HTMLElement {
  const node = element('div', 'endpoint-marker', label)
  node.title = title
  node.setAttribute('aria-label', title)
  return node
}

function checkpointContent(route: RouteResult, index: number, offsetMinutes: number): HTMLElement {
  const content = checkpointPopup(route, route.checkpoints[index], offsetMinutes)
  const root = element('div', 'map-popup')
  root.append(element('p', 'map-popup-title', content.title), element('p', 'map-popup-strong', `Risk: ${content.risk}`))
  content.lines.forEach((line) => root.append(element('p', '', line)))
  if (content.reasons.length > 0) {
    const list = element('ul', '')
    content.reasons.forEach((reason) => list.append(element('li', '', reason)))
    root.append(list)
  }
  return root
}

function routeContent(route: RouteResult): HTMLElement {
  const content = routeSummaryPopup(route)
  const root = element('div', 'map-popup')
  root.append(
    element('p', 'map-popup-title', content.title),
    element('p', 'map-popup-strong', `${content.label} · ${content.status}`),
  )
  content.lines.forEach((line) => root.append(element('p', '', line)))
  return root
}

export function RouteMap({
  routes,
  corridor,
  selectedHour,
  selectedRouteId,
  recommendedRouteId,
  tripOffsetMinutes,
  onSelectRoute,
}: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markersRef = useRef<Marker[]>([])
  const popupRef = useRef<{ popup: Popup; pinned: boolean } | null>(null)
  const [loaded, setLoaded] = useState(false)

  // Latest values for map event handlers, which are registered once.
  const latest = useRef({ routes, tripOffsetMinutes, onSelectRoute, selectedHour })
  useEffect(() => {
    latest.current = { routes, tripOffsetMinutes, onSelectRoute, selectedHour }
  })

  // Built once per analysis result. Selection and hour changes never rebuild them.
  const cumulativeById = useMemo(
    () => new Map(routes.map((route) => [route.id, cumulativeMiles(route.geometry, route.distance_miles)])),
    [routes],
  )

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const map = new MapLibreMap({
      container,
      style: MAP_STYLE_URL,
      center: INITIAL_VIEW.center,
      zoom: INITIAL_VIEW.zoom,
      attributionControl: false,
    })
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new AttributionControl({ compact: false, customAttribution: WEATHER_ATTRIBUTION }), 'bottom-right')

    const clearPopup = () => {
      popupRef.current?.popup.remove()
      popupRef.current = null
    }
    const openPopup = (lngLat: [number, number], content: HTMLElement, pinned: boolean) => {
      clearPopup()
      const popup = new Popup({ closeButton: pinned, closeOnClick: pinned, maxWidth: '280px', offset: 10 })
        .setLngLat(lngLat)
        .setDOMContent(content)
        .addTo(map)
      popupRef.current = { popup, pinned }
    }
    const routeById = (id: unknown) => latest.current.routes.find((route) => route.id === id)
    const overCheckpoint = (event: MapLayerMouseEvent) =>
      map.queryRenderedFeatures(event.point, { layers: CHECKPOINT_LAYERS }).length > 0

    const showCheckpoint = (event: MapLayerMouseEvent, pinned: boolean) => {
      const props = event.features?.[0]?.properties as CheckpointProps | undefined
      const route = props && routeById(props.routeId)
      const checkpoint = route?.checkpoints[props!.index]
      if (!route || !checkpoint) return
      openPopup([checkpoint.lng, checkpoint.lat], checkpointContent(route, props!.index, latest.current.tripOffsetMinutes), pinned)
    }
    const showRoute = (event: MapLayerMouseEvent, pinned: boolean) => {
      const route = routeById(event.features?.[0]?.properties?.id)
      if (!route) return
      openPopup([event.lngLat.lng, event.lngLat.lat], routeContent(route), pinned)
    }

    map.on('load', () => {
      addLayers(map, latest.current.selectedHour)
      for (const layer of CHECKPOINT_LAYERS) {
        map.on('mousemove', layer, (event) => {
          map.getCanvas().style.cursor = 'pointer'
          if (!popupRef.current?.pinned) showCheckpoint(event, false)
        })
        map.on('mouseleave', layer, () => {
          map.getCanvas().style.cursor = ''
          if (popupRef.current && !popupRef.current.pinned) clearPopup()
        })
        map.on('click', layer, (event) => showCheckpoint(event, true))
      }
      map.on('mousemove', 'routes-hit', (event) => {
        map.getCanvas().style.cursor = 'pointer'
        if (!popupRef.current?.pinned && !overCheckpoint(event)) showRoute(event, false)
      })
      map.on('mouseleave', 'routes-hit', () => {
        map.getCanvas().style.cursor = ''
        if (popupRef.current && !popupRef.current.pinned) clearPopup()
      })
      map.on('click', 'routes-hit', (event) => {
        // A checkpoint click opens the checkpoint instead of changing the route.
        if (overCheckpoint(event)) return
        const id = event.features?.[0]?.properties?.id
        if (typeof id !== 'string') return
        latest.current.onSelectRoute(id)
        showRoute(event, true)
      })
      setLoaded(true)
    })

    return () => {
      clearPopup()
      markersRef.current.forEach((marker) => marker.remove())
      map.remove()
      mapRef.current = null
      setLoaded(false)
    }
  }, [])

  // New analysis result: replace every source, endpoint markers, and fit the view.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    setData(map, 'routes', routeFeatures(routes, recommendedRouteId ?? NONE))
    setData(map, 'hazards', allHazardSections(routes, cumulativeById))
    setData(map, 'checkpoints', allCheckpointFeatures(routes))
    setData(map, 'corridor', heatmapFeatures(corridor))
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    popupRef.current?.popup.remove()
    popupRef.current = null
    const first = routes[0]
    if (first && first.geometry.length > 1) {
      markersRef.current = [
        new Marker({ element: endpointMarker('A', 'Origin') }).setLngLat(first.geometry[0]).addTo(map),
        new Marker({ element: endpointMarker('B', 'Destination') }).setLngLat(first.geometry.at(-1)!).addTo(map),
      ]
    }
    const bounds = routesBounds(routes)
    if (bounds) map.fitBounds(bounds, { padding: fitPadding(containerRef.current), duration: 600 })
  }, [routes, corridor, recommendedRouteId, cumulativeById, loaded])

  // Selection change: filters only. No source data changes, no request, no camera move.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    const selectedId = routes.some((route) => route.id === selectedRouteId) ? selectedRouteId! : NONE
    map.setFilter('routes-other-casing', byId('!=', selectedId) as never)
    map.setFilter('routes-other', byId('!=', selectedId) as never)
    map.setFilter('hazard-other', byRoute('!=', selectedId) as never)
    map.setFilter('checkpoints-other', byRoute('!=', selectedId) as never)
    map.setFilter('route-selected-casing', byId('==', selectedId) as never)
    map.setFilter('route-selected', byId('==', selectedId) as never)
    map.setFilter('hazard-selected-casing', byRoute('==', selectedId) as never)
    map.setFilter('hazard-selected', byRoute('==', selectedId) as never)
    map.setFilter('checkpoints-selected', byRoute('==', selectedId) as never)
    map.setFilter('route-recommended', ['all', byId('==', recommendedRouteId ?? NONE), byId('!=', selectedId)] as never)
  }, [routes, selectedRouteId, recommendedRouteId, loaded])

  // Slider hour change: one filter per heat layer. No paint change, no source rebuild.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    for (const level of HEAT_LEVELS) map.setFilter(heatLayerId(level), heatLevelFilter(selectedHour, level) as never)
  }, [selectedHour, loaded])

  // MapLibre's stylesheet makes its container position: relative, so the frame
  // fills the workspace and the map container simply fills the frame.
  return (
    <div className="route-map-frame">
      <div ref={containerRef} className="route-map" role="region" aria-label="Route map" />
    </div>
  )
}
