import type { SimulationState } from '../types'

const apiBaseUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')
const socketBaseUrl = apiBaseUrl
  ? apiBaseUrl.replace(/^http/, 'ws')
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`

export function connectSimulation(id: string, onState: (s: SimulationState) => void, onConnection: (connected: boolean) => void) {
  let disposed = false
  let retry: ReturnType<typeof setTimeout> | undefined
  let socket: WebSocket | undefined
  function connect() {
    socket = new WebSocket(`${socketBaseUrl}/demo/simulations/${id}/ws`)
    socket.onopen = () => onConnection(true)
    socket.onmessage = event => {
      try {
        const data: { state: SimulationState } = JSON.parse(String(event.data))
        if (!disposed) onState(data.state)
      } catch { onConnection(false) }
    }
    socket.onclose = event => {
      if (disposed) return
      onConnection(false)
      if (event.code !== 4404) retry = setTimeout(connect, 1500)
    }
    socket.onerror = () => onConnection(false)
  }
  connect()
  return () => { disposed = true; clearTimeout(retry); socket?.close() }
}
