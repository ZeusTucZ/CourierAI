import type { SimulationState, Shock } from '../types'
import { money, time, difference } from '../format'

export function Header({ state, seed, setSeed, shiftHours = 4, setShiftHours = () => {}, start, control, inject, connected, busy }: { state: SimulationState | null; seed: number; setSeed: (seed: number) => void; shiftHours?: number; setShiftHours?: (hours: number) => void; start: () => void; control: (action: string, speed?: number) => void; inject: (type: Shock['shock_type']) => void; connected: boolean; busy: boolean }) {
  const baseline = state?.agents.baseline?.net_earnings ?? 0
  const smart = state?.agents.smart?.net_earnings ?? 0
  const diff = difference(smart, baseline)
  const running = state?.status === 'running'
  return <header><div className="topbar"><div className="brand"><div className="brand-mark">↗</div><div><h1>Courier AI <span>Simulator</span></h1><p>Monterrey, MX <span className="dot-separator">·</span> Same city. Different decisions.</p></div></div>
    <div className="earnings-comparison"><span className="comparison-label">SMART VS BASELINE</span><div><span className="smart-label">{money(smart)}</span><span className="comparison-vs">vs</span><span>{money(baseline)}</span><strong className={diff.delta < 0 ? 'negative' : 'positive'}>{diff.delta >= 0 ? '+' : '−'}{money(Math.abs(diff.delta))}<small>{diff.percentage === null ? '— %' : `${diff.percentage >= 0 ? '+' : ''}${diff.percentage.toFixed(1)}%`}</small></strong></div></div></div>
    <div className="controls"><label className="seed-control">SEED <input aria-label="Seed" type="number" min="0" max="2147483647" value={seed} disabled={busy || running} onChange={e => setSeed(Number(e.target.value))}/></label>
      <label className="shift-control">SHIFT <select aria-label="Shift duration" value={shiftHours} disabled={busy || running} onChange={e => setShiftHours(Number(e.target.value))}>{[1, 2, 4, 6, 8].map(hours => <option key={hours} value={hours}>{hours} h</option>)}</select></label>
      <div className="clock"><span className="eyebrow">SIMULATED TIME</span><strong>{time(state?.sim_time)}</strong></div>
      <div className="playback"><button className="primary-button" onClick={start} disabled={busy || running || state?.status === 'completed'}>{busy ? 'Preparing…' : '▶ Start'}</button><button className="secondary-button" onClick={() => control('pause')} disabled={!running || busy}>Ⅱ Pause</button><button className="secondary-button" onClick={() => control('complete')} disabled={!state || busy || state.status === 'completed'}>⏩ Simulate shift</button><button className="reset-button" onClick={() => control('reset')} disabled={!state || busy} aria-label="Reset simulation">↺ Reset</button></div>
      <label className="speed-control">Speed <select aria-label="Playback speed" value={state?.speed ?? 25} disabled={!state || busy} onChange={e => control('speed', Number(e.target.value))}>{[1, 5, 10, 25].map(speed => <option key={speed} value={speed}>{speed}x</option>)}</select></label>
      <span className={`stream-indicator ${state && !connected ? 'offline' : ''}`}>{state && !connected ? '● Backend disconnected' : state?.same_stream ? '✓ Same order stream' : '○ Shared-stream simulation'}</span>
      <details className="inject-menu"><summary aria-disabled={!state || busy}>ϟ Inject Event <span>⌄</span></summary><div>{(['rain', 'surge', 'closure', 'delay'] as const).map(type => <button disabled={!state || busy || state.status === 'completed'} key={type} onClick={e => { inject(type); e.currentTarget.closest('details')?.removeAttribute('open') }}>{({ rain: 'Rain', surge: 'Surge', closure: 'Road Closure', delay: 'Delay' })[type]}</button>)}</div></details>
    </div></header>
}
