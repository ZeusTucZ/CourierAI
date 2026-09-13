import { useEffect, useRef, useState } from 'react'
import type { AgentKey, Order, Zone } from '../types'
import { formatReason, time } from '../format'
import { DecisionBadge, useNaturalExplanation } from './DecisionExplanation'

function SmartHistoryReason({ order, sessionId }: { order: Order; sessionId?: string }) {
  const natural = useNaturalExplanation(sessionId, order.order_id)
  const decision = order.decisions.smart
  if (!decision) return null
  return <div className="history-explanation">
    {natural.result ? <><p>{natural.result.explanation}</p><small>{natural.result.source === 'gemini' ? 'Explained with Gemini' : 'Fallback explanation'}</small><details><summary>View original technical reason</summary><p>{formatReason(decision.reason)}</p></details></> : <><button type="button" onClick={() => void natural.load()} disabled={natural.loading || !sessionId}>{natural.loading ? 'Writing…' : '✦ Explain simply'}</button>{natural.error && <small>Could not load the explanation; the original reason remains available.</small>}<small>{formatReason(decision.reason)}</small></>}
  </div>
}

export function AgentOrderHistory({ agent, orders, zones, close, sessionId, revision = 0 }: { agent: AgentKey; orders: Order[]; zones: Map<number, Zone>; close: () => void; sessionId?: string; revision?: number }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [filter, setFilter] = useState<'all' | 'accepted' | 'skipped'>('all')
  const smart = agent === 'smart'
  const accepted = orders.filter(order => order.decisions[agent]?.decision === 'ACCEPT').length
  const skipped = orders.filter(order => order.decisions[agent]?.decision === 'SKIP').length
  const filteredOrders = orders.filter(order => filter === 'all' || order.decisions[agent]?.decision === (filter === 'accepted' ? 'ACCEPT' : 'SKIP'))

  useEffect(() => { dialog.current?.showModal() }, [])

  return <dialog className={`history-modal ${agent}`} ref={dialog} onCancel={close} aria-labelledby={`${agent}-history-title`}>
    <div className="history-heading">
      <div className={`agent-icon ${agent}`}>{smart ? '✦' : '↗'}</div>
      <div><span className="eyebrow">ORDER HISTORY</span><h2 id={`${agent}-history-title`}>{smart ? 'Courier AI' : 'Simple Baseline'}</h2></div>
      <button className="history-close" onClick={close} aria-label="Close history">×</button>
    </div>
    <div className="history-summary"><span aria-label={`${orders.length} orders received`}><strong>{orders.length}</strong> received</span><span className="history-accepted" aria-label={`${accepted} orders accepted`}><strong>{accepted}</strong> accepted</span><span className="history-skipped" aria-label={`${skipped} orders skipped`}><strong>{skipped}</strong> skipped</span></div>
    <div className="history-filters" role="group" aria-label="Filter history">
      <button className={filter === 'all' ? 'active' : ''} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>All <span>{orders.length}</span></button>
      <button className={filter === 'accepted' ? 'active accepted' : 'accepted'} aria-pressed={filter === 'accepted'} onClick={() => setFilter('accepted')}>Accepted <span>{accepted}</span></button>
      <button className={filter === 'skipped' ? 'active skipped' : 'skipped'} aria-pressed={filter === 'skipped'} onClick={() => setFilter('skipped')}>Skipped <span>{skipped}</span></button>
    </div>
    <div className="history-list">
      {filteredOrders.length === 0 && <div className="history-empty"><span>↘</span><h3>{orders.length === 0 ? 'No orders yet' : 'No orders match this filter'}</h3><p>{orders.length === 0 ? 'Orders received by this agent will appear here.' : 'Choose another filter to view the order history.'}</p></div>}
      {[...filteredOrders].reverse().map(order => {
        const decision = order.decisions[agent]
        return <article className="history-order" key={order.order_id}>
          <div className="history-order-top"><strong>{order.order_id}</strong><time>{time(order.sim_time).slice(0, 5)}</time><DecisionBadge decision={decision}/></div>
          <p>{zones.get(order.zone_pickup)?.name ?? `Zone ${order.zone_pickup}`} <span>→</span> {zones.get(order.zone_dropoff)?.name ?? `Zone ${order.zone_dropoff}`}</p>
          {smart ? <SmartHistoryReason key={`${order.order_id}:${revision}`} order={order} sessionId={sessionId}/> : decision?.reason && <small>{formatReason(decision.reason)}</small>}
        </article>
      })}
    </div>
  </dialog>
}
