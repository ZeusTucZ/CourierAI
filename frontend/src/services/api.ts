import type { AgentKey, Decision, SimulationState, Vehicle, ZoneCollection, Shock } from '../types'

// Empty in local development, where Vite proxies requests to FastAPI. Set this
// to the public API URL in Vercel (for example https://courier-api.onrender.com).
const apiBaseUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

async function request<T>(path: string, data?: object): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : undefined)
  if (!response.ok) {
    const body: { detail?: unknown } = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}
export const api = {
  zones: () => request<ZoneCollection>('/geospatial/zones'),
  start: (seed: number, shift_hours: number, vehicle: Vehicle) => request<SimulationState>('/demo/simulations', { seed, shift_hours, vehicle }),
  state: (id: string) => request<SimulationState>(`/demo/simulations/${id}`),
  control: (id: string, action: string, speed?: number) => request<SimulationState>(`/demo/simulations/${id}/control`, { action, ...(speed ? { speed } : {}) }),
  inject: (id: string, shock_type: Shock['shock_type']) => request<SimulationState>(`/demo/simulations/${id}/shocks`, { shock_type }),
  decision: (id: string, order: string) => request<Record<AgentKey, Decision>>(`/demo/simulations/${id}/decisions/${encodeURIComponent(order)}`),
  explanation: (id: string, order: string) => request<DecisionExplanationResult>(`/demo/simulations/${id}/decisions/${encodeURIComponent(order)}/explanation`),
  speechStatus: () => request<{ enabled: boolean }>('/demo/speech/status'),
  routeSpeech: async (id: string, eventId: string, signal: AbortSignal) => {
    const response = await fetch(`${apiBaseUrl}/demo/speech/simulations/${encodeURIComponent(id)}/route-events/${encodeURIComponent(eventId)}`, { method: 'POST', signal })
    if (!response.ok) throw new Error(`Speech unavailable (${response.status})`)
    return response.blob()
  },
  acceptedOrderSpeech: async (id: string, orderId: string, signal: AbortSignal) => {
    const response = await fetch(`${apiBaseUrl}/demo/speech/simulations/${encodeURIComponent(id)}/accepted-orders/${encodeURIComponent(orderId)}`, { method: 'POST', signal })
    if (!response.ok) throw new Error(`Speech unavailable (${response.status})`)
    return response.blob()
  },
}

export interface DecisionExplanationResult {
  structured_reason: string
  llm_explanation: string | null
  explanation: string
  source: 'gemini' | 'fallback'
}
