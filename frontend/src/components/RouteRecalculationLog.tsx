import type { Shock } from '../types'
import { time } from '../format'

const routeEvents = new Set<Shock['shock_type']>(['rain', 'closure', 'delay'])
const eventNames: Record<Shock['shock_type'], string> = {
  rain: 'Rain', closure: 'Road closure', delay: 'Order delay', surge: 'Surge',
}

export function RouteRecalculationLog({ shocks, recalculating }: { shocks: Shock[]; recalculating: boolean }) {
  const events = shocks.filter(shock => routeEvents.has(shock.shock_type)).reverse()
  return <section className="route-log" aria-label="Route recalculation history">
    {recalculating && <p className="route-log-active" role="status"><span className="pulse-dot"/> Recalculating routes…</p>}
    <details>
      <summary>Route recalculation history <span>{events.length}</span></summary>
      <div className="route-log-list">
        {events.length === 0 && <p>No route events yet.</p>}
        {events.map(shock => <article key={shock.id} className="route-log-entry">
          <div><strong>{eventNames[shock.shock_type]}</strong><time>{time(shock.sim_time).slice(0, 5)}</time></div>
          {(['baseline', 'smart'] as const).map(agent => {
            const detours = shock.detours[agent]
            const distance = detours.reduce((sum, detour) => sum + detour.detour_distance_km, 0)
            const minutes = detours.reduce((sum, detour) => sum + detour.detour_minutes, 0)
            return <p key={agent}><b>{agent === 'smart' ? 'Smart' : 'Baseline'}:</b> {detours.length
              ? `Route updated for ${[...new Set(detours.map(detour => detour.order_id))].join(', ')} · ${distance >= 0 ? '+' : ''}${distance.toFixed(2)} km · ${minutes >= 0 ? '+' : ''}${minutes.toFixed(2)} min`
              : 'No active route changed'}</p>
          })}
        </article>)}
      </div>
    </details>
  </section>
}
