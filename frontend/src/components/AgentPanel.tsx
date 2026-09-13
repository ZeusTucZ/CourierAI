import type { AgentKey, AgentState, Order } from '../types'
import { money, time } from '../format'
import { CourierMap } from './CourierMap'
import { DecisionBadge } from './DecisionExplanation'

export function AgentPanel({ agent, state, order, simTime, evaluating, revision }: { agent: AgentKey; state?: AgentState; order?: Order; simTime?: string; evaluating: boolean; revision: number }) {
  const smart = agent === 'smart'
  const decision = order?.decisions[agent]
  const label = state?.status === 'on_break' ? 'ON BREAK' : state?.status === 'waiting' ? 'WAIT' : state?.routes.some(r => r.phase === 'reposition') ? 'REPOSITION' : state?.status === 'to_pickup' ? 'TO PICKUP' : state?.status === 'to_dropoff' ? 'DELIVERING' : 'IDLE'
  return <section className={`agent-panel ${agent}`} aria-label={smart ? 'Smart agent panel' : 'Baseline panel'}>
    <div className="panel-heading"><div className={`agent-icon ${agent}`}>{smart ? '✦' : '↗'}</div><div><h2>{smart ? 'Courier AI' : 'Simple Baseline'}</h2><p>{smart ? 'Smart Agent' : 'First Nearby Order'}</p></div><span className="agent-state">{label}</span></div>
    <CourierMap agent={agent} state={state} revision={revision}/>
    <div className="stats"><div><span>Simulated time</span><strong>{time(simTime).slice(0, 5)}</strong></div><div><span>Net earnings <small>MXN</small></span><strong className={smart ? 'smart-earnings' : ''}>{money(state?.net_earnings ?? 0)}</strong></div></div>
    <div className="current-order"><div><span className="eyebrow">Incoming order</span><strong>{order?.order_id ?? 'Waiting for first order'}</strong></div><DecisionBadge decision={decision} evaluating={evaluating}/></div>
    <div className={`panel-reason ${smart ? 'smart-reason' : ''}`}><span className="eyebrow">{smart ? 'Why?' : 'Recorded reason'}</span><p>{evaluating ? 'Reading the recorded decision…' : decision?.reason ?? (smart ? 'The Smart Agent’s explanation will appear here.' : 'Accepts nearby orders that satisfy the existing constraints.')}</p></div>
    <div className="panel-bottom"><span>Active order <b>{state?.current_order ?? '—'}</b></span><span>{state?.completed ?? 0} completed</span></div>
  </section>
}
