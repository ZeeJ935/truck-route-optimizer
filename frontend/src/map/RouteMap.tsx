import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
  type GeoJSONSource,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { RouteResult } from '../types/api'
import {
  checkpointFeatures,
  checkpointPopup,
  cumulativeMiles,
  hazardSections,
  routeFeatures,
  routesBounds,
  type CheckpointProps,
} from './mapData'
import { MAP_COLORS, MAP_STYLE_URL, WEATHER_ATTRIBUTION } from './mapStyle'

// MapLibre 6 looks for its worker next to its own module file. Vite pre-bundles
// and hashes that file, so point MapLibre at the worker asset Vite emits instead.
setWorkerUrl(maplibreWorkerUrl)

const EMPTY = { type: 'FeatureCollection' as const, features: [] }
const NONE = '__none__'
const INITIAL_VIEW = { center: [-98.5, 39.5] as [number, number], zoom: 3.3 }

interface RouteMapProps {
  routes: RouteResult[]
  selectedRouteId: string | null
  recommendedRouteId: string | null
  tripOffsetMinutes: number
  onSelectRoute: (routeId: string) => void
}

function setData(map: MapLibreMap, sourceId: string, data: unknown) {
  ;(map.getSource(sourceId) as GeoJSONSource | undefined)?.setData(data as Parameters<GeoJSONSource['setData']>[0])
}

function addLayers(map: MapLibreMap) {
  map.addSource('routes', { type: 'geojson', data: EMPTY })
  map.addSource('hazards', { type: 'geojson', data: EMPTY })
  map.addSource('checkpoints', { type: 'geojson', data: EMPTY })

  const lineLayout = { 'line-join': 'round', 'line-cap': 'round' } as const
  // Other routes, muted, under everything else.
  map.addLayer({
    id: 'routes-other-casing',
    type: 'line',
    source: 'routes',
    layout: lineLayout,
    paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.8 },
  })
  map.addLayer({
    id: 'routes-other',
    type: 'line',
    source: 'routes',
    layout: lineLayout,
    paint: { 'line-color': MAP_COLORS.otherRoute, 'line-width': 4, 'line-opacity': 0.6 },
  })
  // The recommended route, when another route is selected: a dashed green line.
  map.addLayer({
    id: 'route-recommended',
    type: 'line',
    source: 'routes',
    layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: { 'line-color': MAP_COLORS.recommended, 'line-width': 4, 'line-dasharray': [2, 1.5] },
    filter: ['==', ['get', 'id'], NONE],
  })
  // The selected route, always above the others so shared highways still show it.
  map.addLayer({
    id: 'route-selected-casing',
    type: 'line',
    source: 'routes',
    layout: lineLayout,
    paint: { 'line-color': '#ffffff', 'line-width': 11 },
    filter: ['==', ['get', 'id'], NONE],
  })
  map.addLayer({
    id: 'route-selected',
    type: 'line',
    source: 'routes',
    layout: lineLayout,
    paint: { 'line-color': MAP_COLORS.selected, 'line-width': 6 },
    filter: ['==', ['get', 'id'], NONE],
  })
  // Severe and No Travel sections of the selected route.
  map.addLayer({
    id: 'hazard-casing',
    type: 'line',
    source: 'hazards',
    layout: lineLayout,
    paint: { 'line-color': MAP_COLORS.hazardCasing, 'line-width': 12 },
  })
  map.addLayer({
    id: 'hazard-line',
    type: 'line',
    source: 'hazards',
    layout: lineLayout,
    paint: {
      'line-color': ['match', ['get', 'level'], 4, MAP_COLORS.risk[4], MAP_COLORS.risk[3]],
      'line-width': 8,
    },
  })
  // Wide invisible lines that make every route easy to click.
  map.addLayer({
    id: 'routes-hit',
    type: 'line',
    source: 'routes',
    layout: lineLayout,
    paint: { 'line-color': '#000000', 'line-width': 18, 'line-opacity': 0 },
  })
  // Checkpoints of the selected route, coloured by risk.
  map.addLayer({
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      // Small at overview zoom so the selected line stays visible at 10-mile spacing;
      // Severe and No Travel checkpoints stay larger at every zoom.
      'circle-radius': [
        'interpolate',
        ['linear'],
        ['zoom'],
        4,
        ['step', ['get', 'risk'], 2.5, 3, 5],
        8,
        ['step', ['get', 'risk'], 5, 3, 7],
        11,
        ['step', ['get', 'risk'], 7, 3, 9],
      ],
      'circle-color': [
        'match',
        ['get', 'risk'],
        0,
        MAP_COLORS.risk[0],
        1,
        MAP_COLORS.risk[1],
        2,
        MAP_COLORS.risk[2],
        3,
        MAP_COLORS.risk[3],
        MAP_COLORS.risk[4],
      ],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 1, 8, 2],
    },
  })
}

function endpointMarker(label: string, title: string): HTMLElement {
  const element = document.createElement('div')
  element.className = 'endpoint-marker'
  element.textContent = label
  element.title = title
  element.setAttribute('aria-label', title)
  return element
}

function popupContent(route: RouteResult, props: CheckpointProps, offsetMinutes: number): HTMLElement {
  const checkpoint = route.checkpoints[props.index]
  const content = checkpointPopup(route, checkpoint, offsetMinutes)
  const root = document.createElement('div')
  root.className = 'checkpoint-popup'
  const title = document.createElement('p')
  title.className = 'checkpoint-popup-title'
  title.textContent = content.title
  const risk = document.createElement('p')
  risk.className = 'checkpoint-popup-risk'
  risk.textContent = `Risk: ${content.risk}`
  root.append(title, risk)
  for (const line of content.lines) {
    const p = document.createElement('p')
    p.textContent = line
    root.append(p)
  }
  if (content.reasons.length > 0) {
    const list = document.createElement('ul')
    for (const reason of content.reasons) {
      const item = document.createElement('li')
      item.textContent = reason
      list.append(item)
    }
    root.append(list)
  }
  return root
}

export function RouteMap({ routes, selectedRouteId, recommendedRouteId, tripOffsetMinutes, onSelectRoute }: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markersRef = useRef<Marker[]>([])
  const popupRef = useRef<{ popup: Popup; pinned: boolean } | null>(null)
  const [loaded, setLoaded] = useState(false)

  // Latest values for map event handlers, which are registered once.
  const latest = useRef({ routes, selectedRouteId, tripOffsetMinutes, onSelectRoute })
  useEffect(() => {
    latest.current = { routes, selectedRouteId, tripOffsetMinutes, onSelectRoute }
  })

  // Display-side distance tables, computed once per analysis result.
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

    const showPopup = (feature: { geometry: unknown; properties: unknown }, pinned: boolean) => {
      const { routes: currentRoutes, selectedRouteId: selected, tripOffsetMinutes: offset } = latest.current
      const route = currentRoutes.find((candidate) => candidate.id === selected)
      if (!route) return
      const props = feature.properties as CheckpointProps
      const checkpoint = route.checkpoints[props.index]
      if (!checkpoint) return
      popupRef.current?.popup.remove()
      const popup = new Popup({ closeButton: pinned, closeOnClick: pinned, maxWidth: '280px', offset: 10 })
        .setLngLat([checkpoint.lng, checkpoint.lat])
        .setDOMContent(popupContent(route, props, offset))
        .addTo(map)
      popupRef.current = { popup, pinned }
    }

    map.on('load', () => {
      addLayers(map)
      map.on('mouseenter', 'checkpoints', (event) => {
        map.getCanvas().style.cursor = 'pointer'
        const feature = event.features?.[0]
        if (feature && !popupRef.current?.pinned) showPopup(feature, false)
      })
      map.on('mouseleave', 'checkpoints', () => {
        map.getCanvas().style.cursor = ''
        if (popupRef.current && !popupRef.current.pinned) {
          popupRef.current.popup.remove()
          popupRef.current = null
        }
      })
      map.on('click', 'checkpoints', (event) => {
        const feature = event.features?.[0]
        if (feature) showPopup(feature, true)
      })
      map.on('mouseenter', 'routes-hit', () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'routes-hit', () => {
        map.getCanvas().style.cursor = ''
      })
      map.on('click', 'routes-hit', (event) => {
        // A checkpoint click opens its popup instead of changing the route.
        if (map.queryRenderedFeatures(event.point, { layers: ['checkpoints'] }).length > 0) return
        const id = event.features?.[0]?.properties?.id
        if (typeof id === 'string') latest.current.onSelectRoute(id)
      })
      setLoaded(true)
    })

    return () => {
      popupRef.current?.popup.remove()
      markersRef.current.forEach((marker) => marker.remove())
      map.remove()
      mapRef.current = null
      setLoaded(false)
    }
  }, [])

  // New analysis result: replace the route lines, endpoint markers, and fit the view.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    setData(map, 'routes', routeFeatures(routes, recommendedRouteId ?? NONE))
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    popupRef.current?.popup.remove()
    popupRef.current = null
    const first = routes[0]
    if (first && first.geometry.length > 1) {
      const origin = first.geometry[0]
      const destination = first.geometry[first.geometry.length - 1]
      markersRef.current = [
        new Marker({ element: endpointMarker('A', 'Origin') }).setLngLat(origin).addTo(map),
        new Marker({ element: endpointMarker('B', 'Destination') }).setLngLat(destination).addTo(map),
      ]
    }
    const bounds = routesBounds(routes)
    if (bounds) map.fitBounds(bounds, { padding: 48, duration: 600 })
  }, [routes, recommendedRouteId, loaded])

  // Selection change: only filters and the selected route's overlays change. No refetch.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    const selected = routes.find((route) => route.id === selectedRouteId)
    const selectedId = selected?.id ?? NONE
    const notSelected = ['!=', ['get', 'id'], selectedId] as const
    map.setFilter('routes-other-casing', notSelected as never)
    map.setFilter('routes-other', notSelected as never)
    map.setFilter('route-selected-casing', ['==', ['get', 'id'], selectedId])
    map.setFilter('route-selected', ['==', ['get', 'id'], selectedId])
    map.setFilter('route-recommended', [
      'all',
      ['==', ['get', 'id'], recommendedRouteId ?? NONE],
      ['!=', ['get', 'id'], selectedId],
    ])
    setData(map, 'hazards', selected ? hazardSections(selected, cumulativeById.get(selected.id)) : EMPTY)
    setData(map, 'checkpoints', selected ? checkpointFeatures(selected) : EMPTY)
    popupRef.current?.popup.remove()
    popupRef.current = null
  }, [routes, selectedRouteId, recommendedRouteId, loaded, cumulativeById])

  // MapLibre's stylesheet makes its container position: relative, so the frame
  // fills the workspace and the map container simply fills the frame.
  return (
    <div className="route-map-frame">
      <div ref={containerRef} className="route-map" role="region" aria-label="Route map" />
    </div>
  )
}
