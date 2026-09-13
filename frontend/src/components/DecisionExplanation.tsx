import { useState } from 'react'
import type { Decision } from '../types'
import { api, type DecisionExplanationResult } from '../services/api'
import { formatReason, money, safety } from '../format'

export function DecisionBadge({ decision, evaluating = false }: { decision?: Decision | null; evaluating?: boolean }) {
  if (evaluating) return <span className="badge evaluating"><span className="pulse-dot"/> Evaluating…</span>
  if (!decision) return <span className="badge waiting">Waiting</span>
  return <span className={`badge ${decision.decision.toLowerCase()}`}>{decision.decision === 'ACCEPT' ? '✓' : '−'} {decision.decision}{safety.has(decision.binding_constraint ?? '') ? ' · SAFETY' : ''}</span>
}

export function useNaturalExplanation(sessionId: string | undefined, orderId: string) {
  const [result, setResult] = useState<DecisionExplanationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  async function load() {
    if (!sessionId || loading || result) return
    setLoading(true)
    setError(false)
    try { setResult(await api.explanation(sessionId, orderId)) }
    catch { setError(true) }
    finally { setLoading(false) }
  }
  return { result, loading, error, load }
}

export function DecisionExplanation({ decision, natural, loading = false, error = false }: { decision?: Decision | null; natural?: DecisionExplanationResult | null; loading?: boolean; error?: boolean }) {
  if (!decision) return <p className="muted">Waiting for the recorded decision.</p>
  const economics = decision.economics
  const technical = <>{decision.binding_constraint && <code className={safety.has(decision.binding_constraint) ? 'safety-text' : ''}>{decision.binding_constraint}</code>}
    {economics && <dl className="economics">
      <div><dt>Net pay</dt><dd>{money(economics.net_pay_mxn)}</dd></div>
      <div><dt>Estimated time</dt><dd>{economics.total_time_min.toFixed(2)} min</dd></div>
      <div><dt>Adjusted rate</dt><dd>{money(economics.adjusted_rate_mxn_hr)}/hr</dd></div>
      <div><dt>Reservation wage</dt><dd>{money(economics.reservation_wage_mxn_hr)}/hr</dd></div>
      {economics.zone_value_mxn_hr !== undefined && <div><dt>Zone value</dt><dd>{money(economics.zone_value_mxn_hr)}/hr</dd></div>}
    </dl>}
    {decision.insertion_feasible === false && <p className="muted">Recorded insertion feasibility: false</p>}</>
  return <div className="explanation">
    <div className="eyebrow">{natural?.source === 'gemini' ? 'Gemini · decision explained' : 'Smart · recorded decision'}</div>
    <p>{loading ? 'Writing a clear explanation…' : natural?.explanation ?? formatReason(decision.reason)}</p>
    {error && <p className="muted">The explanation could not be loaded; the recorded reason is shown.</p>}
    {natural ? <details className="technical-reason"><summary>View original technical reason</summary><p>{formatReason(decision.reason)}</p>{technical}</details> : technical}
  </div>
}
