import { useState } from 'react'
import type { AgentKey, AgentState, Order, Zone } from '../types'
import { money, time } from '../format'
import { CourierMap } from './CourierMap'
import { DecisionBadge } from './DecisionExplanation'
import { AgentOrderHistory } from './AgentOrderHistory'

export function AgentPanel({ agent, state, order, orders = [], zones = new Map(), simTime, evaluating, revision }: { agent: AgentKey; state?: AgentState; order?: Order; orders?: Order[]; zones?: Map<number, Zone>; simTime?: string; evaluating: boolean; revision: number }) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const smart = agent === 'smart'
  const decision = order?.decisions[agent]
  const label = state?.status === 'on_break' ? 'ON BREAK' : state?.status === 'waiting' ? 'WAIT' : state?.routes.some(r => r.phase === 'reposition') ? 'REPOSITION' : state?.status === 'to_pickup' ? 'TO PICKUP' : state?.status === 'to_dropoff' ? 'DELIVERING' : 'IDLE'
  return <section className={`agent-panel ${agent}`} aria-label={smart ? 'Smart agent panel' : 'Baseline panel'}>
    <div className="panel-heading"><div className={`agent-icon ${agent}`}>{smart ? '✦' : '↗'}</div><div><h2>{smart ? 'Courier AI' : 'Simple Baseline'}</h2><p>{smart ? 'Smart Agent' : 'First Nearby Order'}</p></div><span className="agent-state">{label}</span></div>
    <div className="map-panel-wrap">
      <CourierMap agent={agent} state={state} revision={revision}/>
      <div className={`map-current-order ${state?.current_order ? 'active' : ''}`}>
        <span>Orden actual:</span>
        <strong>{state?.current_order ?? 'Sin orden activa'}</strong>
      </div>
    </div>
    <div className="stats"><div><span>Simulated time</span><strong>{time(simTime).slice(0, 5)}</strong></div><div><span>Net earnings <small>MXN</small></span><strong className={smart ? 'smart-earnings' : ''}>{money(state?.net_earnings ?? 0)}</strong></div></div>
    <div className="current-order"><div><span className="eyebrow">Incoming order</span><strong>{order?.order_id ?? 'Waiting for first order'}</strong></div><DecisionBadge decision={decision} evaluating={evaluating}/></div>
    <div className={`panel-reason ${smart ? 'smart-reason' : ''}`}><span className="eyebrow">{smart ? 'Why?' : 'Recorded reason'}</span><p>{evaluating ? 'Reading the recorded decision…' : decision?.reason ?? (smart ? 'The Smart Agent’s explanation will appear here.' : 'Accepts nearby orders that satisfy the existing constraints.')}</p></div>
    <div className="panel-bottom"><button className="history-button" onClick={() => setHistoryOpen(true)}>☰ Ver historial <b>{orders.length}</b></button><span>{state?.completed ?? 0} completed</span></div>
    {historyOpen && <AgentOrderHistory agent={agent} orders={orders} zones={zones} close={() => setHistoryOpen(false)}/>}
  </section>
}
