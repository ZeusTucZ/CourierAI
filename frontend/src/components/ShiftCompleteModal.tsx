import { useEffect, useRef } from 'react'
import type { SimulationState } from '../types'
import { difference, money } from '../format'

export function ShiftCompleteModal({ state, close, reset }: { state: SimulationState; close: () => void; reset: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close() }, [])
  const baseline = state.agents.baseline?.net_earnings ?? 0
  const smart = state.agents.smart?.net_earnings ?? 0
  const diff = difference(smart, baseline)
  return <dialog className="complete-modal" ref={dialog} onCancel={close} aria-labelledby="complete-title"><button className="modal-close" aria-label="Close results" onClick={close}>×</button><div className="complete-symbol">✓</div><div className="eyebrow">SHIFT COMPLETE · SEED {state.seed}</div><h2 id="complete-title">{diff.delta > 0 ? 'Smart wins this shift.' : diff.delta < 0 ? 'Baseline wins this shift.' : 'An even finish.'}</h2><p>Same orders. Results from the simulator.</p><div className="final-earnings"><div><span>Simple Baseline</span><strong>{money(baseline)}</strong></div><div><span>Courier AI</span><strong>{money(smart)}</strong></div></div><div className="final-delta">{diff.delta >= 0 ? '+' : '−'}{money(Math.abs(diff.delta))} <span>{diff.percentage === null ? 'Percentage unavailable with nonpositive baseline' : `${diff.percentage.toFixed(1)}% vs baseline`}</span></div><p className="muted">This demo is simulated. It is not a held-out evaluation.</p><button className="primary-button" onClick={reset}>↺ Replay this shift</button></dialog>
}
