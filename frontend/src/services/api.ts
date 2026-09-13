import type { AgentKey, Decision, SimulationState, ZoneCollection, Shock } from '../types'

async function request<T>(path: string, data?: object): Promise<T> {
  const response = await fetch(path, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : undefined)
  if (!response.ok) {
    const body: { detail?: unknown } = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}
export const api = {
  zones: () => request<ZoneCollection>('/geospatial/zones'),
  start: (seed: number, shift_hours: number) => request<SimulationState>('/demo/simulations', { seed, shift_hours }),
  state: (id: string) => request<SimulationState>(`/demo/simulations/${id}`),
  control: (id: string, action: string, speed?: number) => request<SimulationState>(`/demo/simulations/${id}/control`, { action, ...(speed ? { speed } : {}) }),
  inject: (id: string, shock_type: Shock['shock_type']) => request<SimulationState>(`/demo/simulations/${id}/shocks`, { shock_type }),
  decision: (id: string, order: string) => request<Record<AgentKey, Decision>>(`/demo/simulations/${id}/decisions/${encodeURIComponent(order)}`),
}
