import { memo, useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { AgentKey, AgentState, Coordinates } from '../types'

const start: Coordinates = [-100.289, 25.651]
const latlng = (p: Coordinates): L.LatLngExpression => [p[1], p[0]]
const icon = (label: string, color: string) => L.divIcon({ className: 'map-marker-container', html: `<span class="map-marker" style="--marker-color:${color}">${label}</span>`, iconSize: [32, 32], iconAnchor: [16, 16] })

export const CourierMap = memo(function CourierMap({ agent, state, incomingPickup, revision }: { agent: AgentKey; state?: AgentState; incomingPickup?: Coordinates; revision: number }) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layers = useRef<{ route: L.LayerGroup; closures: L.LayerGroup; courier: L.Marker; pins: L.LayerGroup } | null>(null)
  const [tileError, setTileError] = useState(false)
  useEffect(() => {
    if (!element.current) return
    const instance = L.map(element.current, { zoomControl: false, scrollWheelZoom: false }).setView(latlng(start), 12)
    L.control.zoom({ position: 'bottomright' }).addTo(instance)
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(instance)
    tiles.on('tileerror', () => setTileError(true))
    tiles.on('tileload', () => setTileError(false))
    layers.current = { route: L.layerGroup().addTo(instance), closures: L.layerGroup().addTo(instance), pins: L.layerGroup().addTo(instance), courier: L.marker(latlng(start), { icon: icon('●', agent === 'smart' ? '#0891b2' : '#475569'), zIndexOffset: 1000 }).addTo(instance).bindTooltip(agent === 'smart' ? 'Smart courier' : 'Baseline courier') }
    map.current = instance
    const observer = new ResizeObserver(() => instance.invalidateSize())
    observer.observe(element.current)
    return () => { observer.disconnect(); instance.remove(); map.current = null; layers.current = null }
  }, [agent])
  const frameKey = `${revision}:${state?.version ?? -1}:${state?.closures.features.length ?? 0}:${incomingPickup?.join(',') ?? ''}`
  useEffect(() => {
    const overlay = layers.current
    if (!overlay || !map.current) return
    overlay.route.clearLayers(); overlay.closures.clearLayers(); overlay.pins.clearLayers()
    overlay.courier.setLatLng(latlng(state?.position ?? start))
    const bounds = L.latLngBounds([latlng(state?.position ?? start)])
    for (const route of state?.routes ?? []) {
      const layer = L.geoJSON(route.geometry, { style: { color: agent === 'smart' ? '#0891b2' : '#526176', weight: 4, opacity: .9, dashArray: route.phase === 'reposition' ? '8 6' : undefined } }).addTo(overlay.route)
      bounds.extend(layer.getBounds())
    }
    if (state) L.geoJSON(state.closures, { style: { color: '#e38412', weight: 7, dashArray: '5 6' } }).addTo(overlay.closures)
    const activePins = state?.active_orders?.flatMap((order, index) => [[order.pickup, `R${index + 1}`, '#16826a', `Restaurante ${index + 1} · ${order.order_id}`], [order.dropoff, `D${index + 1}`, '#d86361', `Domicilio ${index + 1} · ${order.order_id}`]] as const) ?? [[state?.pickup, 'R1', '#16826a', 'Restaurante'], [state?.dropoff, 'D1', '#d86361', 'Domicilio']]
    for (const [coordinates, label, color, title] of [...activePins, [incomingPickup, 'R+', '#c67717', 'Restaurante de la orden entrante'], [agent === 'smart' ? state?.target : null, 'T', '#0891b2', 'Target zone']] as const) {
      if (coordinates) { L.marker(latlng(coordinates), { icon: icon(label, color) }).bindTooltip(title).addTo(overlay.pins); bounds.extend(latlng(coordinates)) }
    }
    if (bounds.isValid() && (state?.routes.length || 0) > 0) map.current.fitBounds(bounds, { padding: [45, 45], maxZoom: 14, animate: false })
    // Frame version, not the websocket object identity, controls geometry updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameKey, agent])
  return <div className="map-shell"><div ref={element} className="courier-map" role="img" aria-label={`${agent === 'smart' ? 'Smart' : 'Baseline'} map of Monterrey`} />
    <div className="map-location">◎ Monterrey, Nuevo León</div>
    {tileError && <div className="tile-warning">Map tiles unavailable · route data retained</div>}
    <div className="map-legend"><span><i className={`legend-line ${agent}`}/> Route</span><span><b className="restaurant-dot"/> Nueva orden</span><span><b className="pickup-dot"/> R# restaurante</span><span><b className="dropoff-dot"/> D# domicilio</span></div>
  </div>
})
