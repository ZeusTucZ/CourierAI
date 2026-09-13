import { useLayoutEffect, useRef, useState } from 'react'
import type { Order, Shock, Zone } from '../types'
import { money, time } from '../format'
import { DecisionBadge, DecisionExplanation } from './DecisionExplanation'

export function OrderDecisionCard({ order, zones, evaluating = false }: { order: Order; zones: Map<number, Zone>; evaluating?: boolean }) {
  const { baseline, smart } = order.decisions
  const different = !evaluating && baseline && smart && baseline.decision !== smart.decision
  const baseOffer = order.offers.baseline
  const smartOffer = order.offers.smart
  const delivery = baseOffer?.route_feasible !== false ? baseOffer?.distance_delivery_km : undefined
  const pay = baseOffer ? baseOffer.base_pay_mxn * baseOffer.surge_multiplier + (baseOffer.est_tip_mxn ?? 0) : undefined
  return <article className={`order-card ${different ? 'different' : ''}`}>
    <div className="order-card-top"><strong>{order.order_id}</strong><time>{time(order.sim_time).slice(0, 5)}</time></div>
    <p className="order-destination">{zones.get(order.zone_pickup)?.name ?? `Zone ${order.zone_pickup}`} <span>→</span> {zones.get(order.zone_dropoff)?.name ?? `Zone ${order.zone_dropoff}`}</p>
    <div className="order-numbers"><span>{delivery !== undefined ? `${delivery.toFixed(1)} km delivery` : 'Route unavailable'}</span><strong>{pay !== undefined ? `${money(pay)} est. pay` : '—'}</strong></div>
    {baseOffer && smartOffer && <p className="pickup-distances">Pickup · B {baseOffer.distance_pickup_km.toFixed(1)} km · S {smartOffer.distance_pickup_km.toFixed(1)} km</p>}
    <div className="decision-row"><span>Baseline</span><DecisionBadge decision={baseline} evaluating={evaluating}/></div>
    <div className="decision-row"><span className="smart-label">Smart</span><DecisionBadge decision={smart} evaluating={evaluating}/></div>
    {different && <div className="disagreement">↔ Different decision</div>}
    <details className="why"><summary>Why? <span>Smart explanation</span></summary><DecisionExplanation decision={smart}/></details>
    {baseline && <details className="baseline-why"><summary>Baseline reason</summary><p>{baseline.reason}</p>{baseline.binding_constraint && <code>{baseline.binding_constraint}</code>}</details>}
  </article>
}

export function ShockCard({ shock }: { shock: Shock }) {
  const names = { rain: 'Rain', surge: 'Surge', closure: 'Road closure', delay: 'Order delay' }
  return <article className="shock-card"><div className="order-card-top"><strong>ϟ {names[shock.shock_type]}</strong><time>{time(shock.sim_time).slice(0, 5)}</time></div>
    <p>{shock.shock_type === 'closure' ? 'Upcoming road segment closed' : shock.shock_type === 'rain' ? 'Travel times updated by simulator' : shock.shock_type === 'surge' ? `${shock.multiplier}× pay · Zone ${shock.zone}` : `${shock.order_id} · +${shock.slip_min} min wait`}</p>
    {(['baseline', 'smart'] as const).map(agent => {
      const changes = shock.detours[agent]
      return changes.length > 0 && <p key={agent}>{agent === 'smart' ? 'Smart' : 'Baseline'} route updated: {changes.reduce((s, d) => s + d.detour_distance_km, 0).toFixed(2)} km / {Math.round(changes.reduce((s, d) => s + d.detour_minutes, 0) * 60)} sec change</p>
    })}
  </article>
}

export function OrdersFeed({ orders, shocks, zones, evaluating }: { orders: Order[]; shocks: Shock[]; zones: Map<number, Zone>; evaluating: string | null }) {
  const feed = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  const [unseen, setUnseen] = useState(false)
  const entries = [...orders.map(order => ({ id: order.order_id, at: order.sim_time, order, shock: null })), ...shocks.map(shock => ({ id: shock.id, at: shock.sim_time, order: null, shock }))].sort((a, b) => b.at.localeCompare(a.at))
  const previous = useRef({ id: '', height: 0 })
  const newest = entries[0]?.id ?? ''
  useLayoutEffect(() => {
    const element = feed.current
    if (!element) return
    if (newest !== previous.current.id) {
      if (pinned.current) { element.scrollTop = 0; setUnseen(false) }
      else { element.scrollTop += element.scrollHeight - previous.current.height; setUnseen(true) }
    }
    previous.current = { id: newest, height: element.scrollHeight }
  }, [newest, orders, shocks])
  return <aside className="orders-panel"><div className="feed-heading"><div><h2>Orders <span>{orders.length}</span></h2><p>One stream. Two decisions.</p></div><span className="live-dot"/></div>
    {unseen && <button className="latest-button" onClick={() => { feed.current?.scrollTo({ top: 0, behavior: 'smooth' }); pinned.current = true; setUnseen(false) }}>↑ New arrivals</button>}
    <div className="feed" ref={feed} onScroll={() => { pinned.current = (feed.current?.scrollTop ?? 0) < 24 }}>
      {entries.length === 0 && <div className="feed-empty"><span>↘</span><h3>Watch the decisions unfold</h3><p>Start a shift. Every incoming order will appear here with both agents’ decisions.</p></div>}
      {entries.map(entry => entry.order ? <OrderDecisionCard key={entry.id} order={entry.order} zones={zones} evaluating={evaluating === entry.id}/> : <ShockCard key={entry.id} shock={entry.shock!}/>)}
    </div><div className="feed-footer">Explanations from recorded decisions · no LLM</div>
  </aside>
}
