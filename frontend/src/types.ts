import type { FeatureCollection, LineString, MultiLineString } from 'geojson'

export type AgentKey = 'baseline' | 'smart'
export type Coordinates = [number, number]
export interface Route { order_id: string | null; phase: string; geometry: LineString; edge_path: number[][]; destination_node: number; distance_km: number; eta_min: number }
export interface ActiveOrder { order_id: string; phase: string; pickup: Coordinates; dropoff: Coordinates; is_current: boolean }
export interface Economics { net_pay_mxn: number; total_time_min: number; adjusted_rate_mxn_hr: number; reservation_wage_mxn_hr: number; operating_cost_mxn: number; zone_value_mxn_hr?: number; opportunity_cost_mxn?: number }
export interface Decision { order_id: string; sim_time: string; decision: 'ACCEPT' | 'SKIP'; reason: string; binding_constraint: string | null; economics?: Economics; delivery_deadline?: string; insertion_feasible?: boolean }
export interface Offer { zone_pickup: number; zone_dropoff: number; distance_pickup_km: number; distance_delivery_km: number; base_pay_mxn: number; surge_multiplier: number; est_tip_mxn?: number; route_feasible?: boolean }
export interface Order { order_id: string; sim_time: string; zone_pickup: number; zone_dropoff: number; decisions: Record<AgentKey, Decision | null>; offers: Record<AgentKey, Offer | null> }
export interface Detour { order_id: string; detour_distance_km: number; detour_minutes: number }
export interface Shock { id: string; sim_time: string; shock_type: 'rain' | 'surge' | 'closure' | 'delay'; road?: string; zone?: number; order_id?: string; multiplier?: number; duration_min?: number; slip_min?: number; detours: Record<AgentKey, Detour[]> }
export interface Metrics { net_earnings_mxn: number; orders_completed: number; safety_violations: number; [key: string]: number }
export interface AgentState { version: number; position: Coordinates; zone: number; status: string; action: string | null; net_earnings: number; current_order: string | null; active_orders?: ActiveOrder[]; pickup: Coordinates | null; dropoff: Coordinates | null; target: Coordinates | null; routes: Route[]; closures: FeatureCollection<MultiLineString>; completed: number }
export interface SimulationState { id: string; seed: number; shift_hours?: number; status: 'preparing' | 'running' | 'paused' | 'updating' | 'completed' | 'error'; speed: number; error: string | null; revision: number; sim_time?: string; start_time?: string; end_time?: string; elapsed_seconds?: number; same_stream: boolean; provenance?: string; baseline_threshold?: number; agents: Partial<Record<AgentKey, AgentState>>; orders: Order[]; shocks: Shock[]; metrics?: Record<AgentKey, Metrics> | null }
export interface Zone { zone_id: number; name: string; latitude: number; longitude: number }
export interface ZoneCollection { features: { properties: Zone }[] }
