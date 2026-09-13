import type { Decision } from '../types'
import { money, safety } from '../format'

export function DecisionBadge({ decision, evaluating = false }: { decision?: Decision | null; evaluating?: boolean }) {
  if (evaluating) return <span className="badge evaluating"><span className="pulse-dot"/> Evaluating…</span>
  if (!decision) return <span className="badge waiting">Waiting</span>
  return <span className={`badge ${decision.decision.toLowerCase()}`}>{decision.decision === 'ACCEPT' ? '✓' : '−'} {decision.decision}{safety.has(decision.binding_constraint ?? '') ? ' · SAFETY' : ''}</span>
}

export function DecisionExplanation({ decision }: { decision?: Decision | null }) {
  if (!decision) return <p className="muted">Waiting for the recorded decision.</p>
  const economics = decision.economics
  return <div className="explanation">
    <div className="eyebrow">Smart decision · from decision log</div>
    <p>{decision.reason}</p>
    {decision.binding_constraint && <code className={safety.has(decision.binding_constraint) ? 'safety-text' : ''}>{decision.binding_constraint}</code>}
    {economics && <dl className="economics">
      <div><dt>Net pay</dt><dd>{money(economics.net_pay_mxn)}</dd></div>
      <div><dt>Estimated time</dt><dd>{economics.total_time_min.toFixed(1)} min</dd></div>
      <div><dt>Adjusted rate</dt><dd>{money(economics.adjusted_rate_mxn_hr)}/hr</dd></div>
      <div><dt>Reservation wage</dt><dd>{money(economics.reservation_wage_mxn_hr)}/hr</dd></div>
      {economics.zone_value_mxn_hr !== undefined && <div><dt>Zone value</dt><dd>{money(economics.zone_value_mxn_hr)}/hr</dd></div>}
    </dl>}
    {decision.insertion_feasible === false && <p className="muted">Recorded insertion feasibility: false</p>}
  </div>
}
