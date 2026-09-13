import { useEffect, useRef, useState } from 'react'
import type { SimulationState, Zone, Shock } from './types'
import { api } from './services/api'
import { connectSimulation } from './services/socket'
import { Header } from './components/Header'
import { AgentPanel } from './components/AgentPanel'
import { OrdersFeed } from './components/OrdersFeed'
import { ShiftCompleteModal } from './components/ShiftCompleteModal'

export default function App() {
  const [state, setState] = useState<SimulationState | null>(null)
  const [seed, setSeed] = useState(202635)
  const [shiftHours, setShiftHours] = useState(4)
  const [zones, setZones] = useState(new Map<number, Zone>())
  const [connected, setConnected] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [evaluating, setEvaluating] = useState<string | null>(null)
  const [banner, setBanner] = useState<Shock | null>(null)
  const [routeUpdate, setRouteUpdate] = useState(false)
  const [speechEnabled, setSpeechEnabled] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const lastShock = useRef('')
  const spokenSession = useRef<string | null>(null)
  const seenRouteEvents = useRef(new Set<string>())
  const spokenAcceptedOrders = useRef(new Set<string>())
  const silentFastForward = useRef(false)
  const speechRequest = useRef<AbortController | null>(null)
  const speechAudio = useRef<HTMLAudioElement | null>(null)
  const speechUrl = useRef<string | null>(null)
  const latest = state?.orders.at(-1)
  function stopSpeech() {
    speechRequest.current?.abort()
    speechRequest.current = null
    speechAudio.current?.pause()
    speechAudio.current = null
    if (speechUrl.current) URL.revokeObjectURL(speechUrl.current)
    speechUrl.current = null
  }
  useEffect(() => { api.speechStatus().then(result => setSpeechEnabled(result.enabled)).catch(() => setSpeechEnabled(false)) }, [])
  useEffect(() => () => stopSpeech(), [])
  useEffect(() => {
    if (!state?.id) return
    if (spokenSession.current !== state.id) {
      stopSpeech()
      spokenSession.current = state.id
      seenRouteEvents.current = new Set(state.shocks.map(shock => shock.id))
      spokenAcceptedOrders.current = new Set(state.orders
        .filter(order => order.decisions.smart?.decision === 'ACCEPT')
        .map(order => order.order_id))
      silentFastForward.current = false
      return
    }
    const fresh = state.shocks.filter(shock => !seenRouteEvents.current.has(shock.id))
    state.shocks.forEach(shock => seenRouteEvents.current.add(shock.id))
    if (state.status === 'completed') { stopSpeech(); return }
    if (!speechEnabled || silentFastForward.current) return
    const event = fresh.reverse().find(shock => shock.shock_type === 'rain' || shock.shock_type === 'closure' || shock.shock_type === 'delay')
    if (!event) return
    stopSpeech()
    const controller = new AbortController()
    speechRequest.current = controller
    void api.routeSpeech(state.id, event.id, controller.signal).then(blob => {
      if (controller.signal.aborted || silentFastForward.current) return
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      speechUrl.current = url
      speechAudio.current = audio
      audio.onended = () => { if (speechAudio.current === audio) stopSpeech() }
      void audio.play().catch(() => {
        if (speechAudio.current === audio) stopSpeech()
        setError('Browser blocked route-event audio. Click Start, then allow sound for this tab.')
      })
    }).catch(() => setError('Route-event voice is unavailable. Check the backend and ElevenLabs configuration.'))
  }, [state?.id, state?.shocks, state?.status, speechEnabled])
  useEffect(() => {
    if (!state?.id || !speechEnabled || silentFastForward.current || state.status === 'completed') return
    const accepted = state.orders.find(order => order.decisions.smart?.decision === 'ACCEPT' && !spokenAcceptedOrders.current.has(order.order_id))
    if (!accepted) return
    // Record before requesting audio: WebSocket updates arrive four times a second.
    spokenAcceptedOrders.current.add(accepted.order_id)
    stopSpeech()
    const controller = new AbortController()
    speechRequest.current = controller
    void api.acceptedOrderSpeech(state.id, accepted.order_id, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      speechUrl.current = url
      speechAudio.current = audio
      audio.onended = () => { if (speechAudio.current === audio) stopSpeech() }
      void audio.play().catch(() => {
        if (speechAudio.current === audio) stopSpeech()
        setError('Browser blocked order audio. Click Start, then allow sound for this tab.')
      })
    }).catch(() => setError('Order voice is unavailable. Check the backend and ElevenLabs configuration.'))
  }, [state?.id, state?.orders, state?.status, speechEnabled])
  useEffect(() => {
    const identifier = localStorage.getItem('courier-demo-session')
    if (identifier) api.state(identifier).then(saved => { setState(saved); setSeed(saved.seed); setShiftHours(saved.shift_hours ?? 4) }).catch(() => localStorage.removeItem('courier-demo-session'))
  }, [])
  useEffect(() => { if (state?.id) localStorage.setItem('courier-demo-session', state.id) }, [state?.id])
  useEffect(() => { api.zones().then(data => setZones(new Map(data.features.map(f => [f.properties.zone_id, f.properties])))).catch(() => setError('Could not load zones. Check that the backend is running.')) }, [])
  useEffect(() => {
    if (!state?.id) return
    return connectSimulation(state.id, setState, setConnected)
  }, [state?.id])
  useEffect(() => {
    if (!latest) { setEvaluating(null); return }
    setEvaluating(latest.order_id)
    const timer = setTimeout(() => setEvaluating(null), 700)
    return () => clearTimeout(timer)
  }, [latest?.order_id])
  const newestShock = state?.shocks.at(-1)
  useEffect(() => {
    if (routeUpdate && !pending && state?.status !== 'updating') setRouteUpdate(false)
  }, [routeUpdate, pending, state?.status])
  useEffect(() => {
    if (!newestShock) { lastShock.current = ''; setBanner(null); return }
    if (lastShock.current === newestShock.id) return
    lastShock.current = newestShock.id
    setBanner(newestShock)
    const timer = setTimeout(() => setBanner(null), 6500)
    return () => clearTimeout(timer)
  }, [newestShock?.id])
  const busy = pending || state?.status === 'preparing' || state?.status === 'updating'
  async function perform(work: () => Promise<SimulationState>) {
    setPending(true); setError(null)
    try { setState(await work()) } catch (e) { setError(e instanceof Error ? e.message : 'Could not reach backend') }
    finally { setPending(false) }
  }
  function start() {
    silentFastForward.current = false
    if (state && state.seed === seed && state.shift_hours === shiftHours && state.status !== 'error') void perform(() => api.control(state.id, 'start'))
    else { setDismissed(false); void perform(() => api.start(seed, shiftHours)) }
  }
  function control(action: string, speed?: number) {
    if (!state) return
    if (action === 'complete' || action === 'reset') { silentFastForward.current = true; stopSpeech() }
    if (action === 'reset') seenRouteEvents.current.clear()
    if (action === 'reset') { setDismissed(false); lastShock.current = ''; setBanner(null) }
    void perform(() => api.control(state.id, action, speed))
  }
  function inject(type: Shock['shock_type']) {
    if (!state) return
    setRouteUpdate(type === 'rain' || type === 'closure' || type === 'delay')
    void perform(() => api.inject(state.id, type))
  }
  const progress = state?.start_time && state.end_time ? (state.elapsed_seconds ?? 0) / ((Date.parse(state.end_time) - Date.parse(state.start_time)) / 1000) * 100 : 0
  return <div className="app-shell"><Header state={state} seed={seed} setSeed={setSeed} shiftHours={shiftHours} setShiftHours={setShiftHours} start={start} control={control} inject={inject} connected={connected} busy={!!busy}/>
    <div className="shift-progress"><div style={{ width: `${progress}%` }}/></div>
    {(error || state?.error) && <div className="error-banner" role="alert">{error || state?.error}<button onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}
    <div className="story-bar"><span>{busy ? <><span className="pulse-dot"/>{routeUpdate ? 'Recalculating routes… playback paused' : state?.status === 'updating' ? 'Applying event in the simulator… playback paused' : 'Preparing the OSM-backed shift…'}</> : latest ? <><b className="new-order-tag">NEW ORDER</b><strong>{latest.order_id}</strong><span>{zones.get(latest.zone_pickup)?.name ?? `Zone ${latest.zone_pickup}`} → {zones.get(latest.zone_dropoff)?.name ?? `Zone ${latest.zone_dropoff}`}</span></> : <><span className="live-dot"/> Two couriers. One shared order stream.</>}</span><small>{state?.status === 'paused' ? 'Ⅱ Playback paused' : state?.status === 'completed' ? '✓ Shift complete' : 'Watch what each agent chooses — and why.'}</small></div>
    {banner && <div className="shock-banner" role="status">ϟ <strong>{({ rain: 'Rain detected', surge: 'Surge activated', closure: 'Road closure detected', delay: 'Order delay' })[banner.shock_type]}</strong><span>{banner.detours.smart.length || banner.detours.baseline.length ? 'Active routes updated · see the event in Orders' : 'Simulator event received · see Orders for its effects'}</span></div>}
    <main className="workspace"><AgentPanel agent="baseline" state={state?.agents.baseline} order={latest} orders={state?.orders ?? []} zones={zones} simTime={state?.sim_time} evaluating={evaluating !== null} revision={state?.revision ?? 0} sessionId={state?.id}/><AgentPanel agent="smart" state={state?.agents.smart} order={latest} orders={state?.orders ?? []} zones={zones} simTime={state?.sim_time} evaluating={evaluating !== null} revision={state?.revision ?? 0} sessionId={state?.id}/><OrdersFeed orders={state?.orders ?? []} shocks={state?.shocks ?? []} zones={zones} evaluating={evaluating} sessionId={state?.id} revision={state?.revision ?? 0} recalculating={routeUpdate && busy}/></main>
    <footer className="page-footer"><span>INFOSYS HACKATHON <span> / </span> Courier decision demo</span><span>{state?.provenance ? state.provenance.startsWith('Frozen') ? 'Calibrated configuration · simulated results' : 'Illustrative simulation · not a held-out evaluation' : 'Real road geometry · simulated orders and earnings'}</span><span>MXN · 1x = 1 simulated sec / sec</span></footer>
    {state?.status === 'completed' && !dismissed && <ShiftCompleteModal state={state} close={() => setDismissed(true)} reset={() => control('reset')}/>}
  </div>
}
