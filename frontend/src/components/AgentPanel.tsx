import { useState } from 'react'
import type { AgentKey, AgentState, Coordinates, Decision, Order, Zone } from '../types'
import { formatReason, money, time } from '../format'
import { CourierMap } from './CourierMap'
import { DecisionBadge, useNaturalExplanation } from './DecisionExplanation'
import { AgentOrderHistory } from './AgentOrderHistory'

function SmartPanelReason({ decision, orderId, sessionId, evaluating }: { decision?: Decision | null; orderId: string; sessionId?: string; evaluating: boolean }) {
  const natural = useNaturalExplanation(sessionId, orderId)
  return <div className="panel-reason smart-reason"><span className="eyebrow">Why?</span>
    <p>{evaluating ? 'Reading the recorded decision…' : natural.loading ? 'Writing a clear explanation…' : natural.result?.explanation ?? (decision?.reason ? formatReason(decision.reason) : 'The Smart Agent’s explanation will appear here.')}</p>
    {decision && !evaluating && <button type="button" className="explain-button" onClick={() => void natural.load()} disabled={natural.loading || !!natural.result || !sessionId}>{natural.result ? natural.result.source === 'gemini' ? '✦ Explained with Gemini' : 'Fallback explanation' : '✦ Explain simply'}</button>}
    {natural.result && <details className="technical-reason"><summary>View original technical reason</summary><p>{decision?.reason && formatReason(decision.reason)}</p></details>}
    {natural.error && <small className="muted">The explanation could not be loaded.</small>}
  </div>
}

export function AgentPanel({ agent, state, order, orders = [], zones = new Map(), simTime, evaluating, revision, sessionId }: { agent: AgentKey; state?: AgentState; order?: Order; orders?: Order[]; zones?: Map<number, Zone>; simTime?: string; evaluating: boolean; revision: number; sessionId?: string }) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const smart = agent === 'smart'
  const decision = order?.decisions[agent]
  const activeOrders = state?.active_orders ?? []
  const restaurant = order ? zones.get(order.zone_pickup) : undefined
  const incomingPickup: Coordinates | undefined = restaurant ? [restaurant.longitude, restaurant.latitude] : undefined
  const label = state?.status === 'on_break' ? 'ON BREAK' : state?.status === 'waiting' ? 'WAIT' : state?.routes.some(r => r.phase === 'reposition') ? 'REPOSITION' : state?.status === 'to_pickup' ? 'TO PICKUP' : state?.status === 'to_dropoff' ? 'DELIVERING' : 'IDLE'
  return <section className={`agent-panel ${agent}`} aria-label={smart ? 'Smart agent panel' : 'Baseline panel'}>
    <div className="panel-heading"><div className={`agent-icon ${agent}`}>{smart ? '✦' : '↗'}</div><div><h2>{smart ? 'Courier AI' : 'Simple Baseline'}</h2><p>{smart ? 'Smart Agent' : 'First Nearby Order'}</p></div><span className="agent-state">{label}</span></div>
    <div className="map-panel-wrap">
      <CourierMap agent={agent} state={state} incomingPickup={incomingPickup} revision={revision}/>
      <div className={`map-current-order ${state?.current_order ? 'active' : ''}`}>
        <span>Current order:</span>
        <strong>{state?.current_order ?? 'No active order'}</strong>
      </div>
    </div>
    <div className="stats"><div><span>Simulated time</span><strong>{time(simTime).slice(0, 5)}</strong></div><div><span>Net earnings <small>MXN</small></span><strong className={smart ? 'smart-earnings' : ''}>{money(state?.net_earnings ?? 0)}</strong></div></div>
    {activeOrders.length > 0 && <div className="active-orders" aria-label={`${activeOrders.length} active orders`}><div><span className="eyebrow">Active orders</span><b>{activeOrders.length}</b></div><ul>{activeOrders.map((active, index) => <li key={active.order_id} className={active.is_current ? 'current' : ''}><strong>#{index + 1} · {active.order_id}</strong><span>{active.phase === 'to_pickup' ? 'Heading to restaurant' : active.phase === 'waiting' ? 'Waiting at restaurant' : active.phase === 'to_dropoff' ? 'Heading to customer' : 'Delivering'}</span></li>)}</ul></div>}
    <div className="current-order"><div><span className="eyebrow">Incoming order</span><strong>{order?.order_id ?? 'Waiting for first order'}</strong></div><DecisionBadge decision={decision} evaluating={evaluating}/></div>
    {smart ? <SmartPanelReason key={`${order?.order_id ?? 'none'}:${revision}`} decision={decision} orderId={order?.order_id ?? ''} sessionId={sessionId} evaluating={evaluating}/> : <div className="panel-reason"><span className="eyebrow">Recorded reason</span><p>{evaluating ? 'Reading the recorded decision…' : decision?.reason ? formatReason(decision.reason) : 'Accepts nearby orders that satisfy the existing constraints.'}</p></div>}
    <div className="panel-bottom"><button className="history-button" onClick={() => setHistoryOpen(true)}>☰ View history <b>{orders.length}</b></button><span>{state?.completed ?? 0} completed</span></div>
    {historyOpen && <AgentOrderHistory agent={agent} orders={orders} zones={zones} close={() => setHistoryOpen(false)} sessionId={sessionId} revision={revision}/>}
  </section>
}
