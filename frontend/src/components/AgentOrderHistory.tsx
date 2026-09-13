import { useEffect, useRef, useState } from 'react'
import type { AgentKey, Order, Zone } from '../types'
import { time } from '../format'
import { DecisionBadge } from './DecisionExplanation'

export function AgentOrderHistory({ agent, orders, zones, close }: { agent: AgentKey; orders: Order[]; zones: Map<number, Zone>; close: () => void }) {
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
      <div><span className="eyebrow">HISTORIAL DE PEDIDOS</span><h2 id={`${agent}-history-title`}>{smart ? 'Courier AI' : 'Simple Baseline'}</h2></div>
      <button className="history-close" onClick={close} aria-label="Cerrar historial">×</button>
    </div>
    <div className="history-summary"><span aria-label={`${orders.length} pedidos recibidos`}><strong>{orders.length}</strong> recibidos</span><span className="history-accepted" aria-label={`${accepted} pedidos aceptados`}><strong>{accepted}</strong> aceptados</span><span className="history-skipped" aria-label={`${skipped} pedidos omitidos`}><strong>{skipped}</strong> omitidos</span></div>
    <div className="history-filters" role="group" aria-label="Filtrar historial">
      <button className={filter === 'all' ? 'active' : ''} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>Todos <span>{orders.length}</span></button>
      <button className={filter === 'accepted' ? 'active accepted' : 'accepted'} aria-pressed={filter === 'accepted'} onClick={() => setFilter('accepted')}>Aceptados <span>{accepted}</span></button>
      <button className={filter === 'skipped' ? 'active skipped' : 'skipped'} aria-pressed={filter === 'skipped'} onClick={() => setFilter('skipped')}>Omitidos <span>{skipped}</span></button>
    </div>
    <div className="history-list">
      {filteredOrders.length === 0 && <div className="history-empty"><span>↘</span><h3>{orders.length === 0 ? 'Aún no hay pedidos' : 'No hay pedidos en este filtro'}</h3><p>{orders.length === 0 ? 'Los pedidos recibidos por este modelo aparecerán aquí.' : 'Selecciona otro filtro para consultar el historial.'}</p></div>}
      {[...filteredOrders].reverse().map(order => {
        const decision = order.decisions[agent]
        return <article className="history-order" key={order.order_id}>
          <div className="history-order-top"><strong>{order.order_id}</strong><time>{time(order.sim_time).slice(0, 5)}</time><DecisionBadge decision={decision}/></div>
          <p>{zones.get(order.zone_pickup)?.name ?? `Zona ${order.zone_pickup}`} <span>→</span> {zones.get(order.zone_dropoff)?.name ?? `Zona ${order.zone_dropoff}`}</p>
          {decision?.reason && <small>{decision.reason}</small>}
        </article>
      })}
    </div>
  </dialog>
}
