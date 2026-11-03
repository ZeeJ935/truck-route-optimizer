// A recording stand-in for maplibre-gl. jsdom has no WebGL, so tests use this to
// check which sources, layers, filters, and camera moves the map component asks for.

type Handler = (event?: unknown) => void

class FakeSource {
  data: unknown
  setDataCalls = 0

  constructor(data: unknown) {
    this.data = data
  }

  setData(data: unknown) {
    this.data = data
    this.setDataCalls += 1
    return this
  }
}

export class Map {
  static instances: Map[] = []

  options: unknown
  handlers: Record<string, Handler[]> = {}
  sources: Record<string, FakeSource> = {}
  addSourceCalls: string[] = []
  layers: { id: string; filter?: unknown }[] = []
  filters: Record<string, unknown> = {}
  fitBoundsCalls: unknown[][] = []
  removed = false
  canvas = { style: { cursor: '' } }

  constructor(options: unknown) {
    this.options = options
    Map.instances.push(this)
    queueMicrotask(() => this.emit('load'))
  }

  on(type: string, layerOrHandler: string | Handler, handler?: Handler) {
    const key = typeof layerOrHandler === 'string' ? `${type}:${layerOrHandler}` : type
    const fn = typeof layerOrHandler === 'string' ? handler! : layerOrHandler
    ;(this.handlers[key] ??= []).push(fn)
    return this
  }

  emit(type: string, layer?: string, event?: unknown) {
    const key = layer ? `${type}:${layer}` : type
    for (const handler of this.handlers[key] ?? []) handler(event)
  }

  addSource(id: string, spec: { data: unknown }) {
    this.addSourceCalls.push(id)
    this.sources[id] = new FakeSource(spec.data)
    return this
  }

  getSource(id: string) {
    return this.sources[id]
  }

  addLayer(layer: { id: string; filter?: unknown }) {
    this.layers.push(layer)
    if (layer.filter) this.filters[layer.id] = layer.filter
    return this
  }

  setFilter(id: string, filter: unknown) {
    this.filters[id] = filter
    return this
  }

  fitBounds(...args: unknown[]) {
    this.fitBoundsCalls.push(args)
    return this
  }

  addControl() {
    return this
  }

  getCanvas() {
    return this.canvas
  }

  queryRenderedFeatures() {
    return []
  }

  remove() {
    this.removed = true
  }
}

export class Popup {
  removed = false
  setLngLat() {
    return this
  }
  setDOMContent() {
    return this
  }
  addTo() {
    return this
  }
  remove() {
    this.removed = true
    return this
  }
}

export class Marker {
  setLngLat() {
    return this
  }
  addTo() {
    return this
  }
  remove() {
    return this
  }
}

export class NavigationControl {}
export class AttributionControl {}

export function setWorkerUrl(url: string) {
  workerUrls.push(url)
}

export const workerUrls: string[] = []
