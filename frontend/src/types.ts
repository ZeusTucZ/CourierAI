export interface DecisionInspectorData {
  order_id: string;
  sim_time: string;
  offer_details: {
    platform: string;
    zone_pickup: number;
    zone_dropoff: number;
    distance_pickup_km: number;
    distance_delivery_km: number;
    distance_total_km: number;
    base_pay_mxn: number;
    est_tip_mxn: number;
    surge_multiplier: number;
    restaurant_prep_min: number;
    weight_kg: number;
    volume_liters: number;
  };
  baseline: {
    decision: string;
    reason: string;
    binding_constraint: string | null;
    threshold_km: number;
  };
  smart: {
    decision: string;
    reason: string;
    binding_constraint: string | null;
    economics: {
      gross_pay_mxn: number | null;
      operating_cost_mxn: number | null;
      net_pay_mxn: number | null;
      raw_rate_mxn_hr: number | null;
      adjusted_rate_mxn_hr: number | null;
      reservation_wage_mxn_hr: number | null;
      deadhead_km: number | null;
      zone_value_mxn_hr: number | null;
      opportunity_cost_mxn: number | null;
      stacking_impact_min: number | null;
    };
    historical_signal: any | null;
  };
}

export interface ActiveOrderInfo {
  order_id: string;
  pickup_zone: number;
  dropoff_zone: number;
  promised_time: string;
}

export interface AgentState {
  name: string;
  net_earnings_mxn: number;
  gross_earnings_mxn: number;
  operating_costs_mxn: number;
  current_zone: number;
  status: string;
  orders_completed: number;
  orders_accepted: number;
  orders_skipped: number;
  distance_traveled_km: number;
  idle_time_min: number;
  late_deliveries: number;
  safety_violations: number;
  mxn_per_hour: number;
  mxn_per_km: number;
  active_orders: ActiveOrderInfo[];
  reposition_distance_km?: number;
  reposition_count?: number;
  last_decision: {
    decision: string;
    reason: string;
    binding_constraint?: string | null;
    adjusted_rate_mxn_hr?: number | null;
    reservation_wage_mxn_hr?: number | null;
  };
}

export interface IncomingOrderInfo {
  order_id: string;
  sim_time: string;
  platform: string;
  zone_pickup: number;
  zone_dropoff: number;
  distance_pickup_km: number;
  distance_delivery_km: number;
  distance_total_km: number;
  base_pay_mxn: number;
  est_tip_mxn: number;
  surge_multiplier: number;
  restaurant_prep_min: number;
  weight_kg: number;
  baseline_decision: string;
  smart_decision: string;
  is_disagreement: boolean;
  agreement_summary: string;
  smart_reason: string;
}

export interface ShockInfo {
  shock_type: string;
  sim_time: string;
  duration_min?: number;
  message: string;
}

export interface ShockReactionInfo {
  shock_type: string;
  sim_time: string;
  smart_reaction: string;
  baseline_reaction: string;
}

export interface SimulationState {
  sim_time: string;
  sim_time_iso: string;
  shift_start: string;
  shift_end: string;
  status: 'idle' | 'running' | 'paused' | 'completed';
  seed: number;
  vehicle: string;
  stream_hash: string;
  playback_speed: number;
  current_shock: ShockInfo | null;
  latest_shock_reaction: ShockReactionInfo | null;
  incoming_order: IncomingOrderInfo | null;
  comparison: {
    leader: 'Smart' | 'Baseline' | 'Tie';
    net_difference: number;
    uplift_pct: number;
    is_smart_winning: boolean;
  };
  baseline: AgentState;
  smart: AgentState;
}

export interface TimelineEventItem {
  id: number;
  sim_time: string;
  sim_time_iso: string;
  type: string;
  title: string;
  description: string;
  level: 'info' | 'warning' | 'success' | 'danger';
  order_id?: string;
  is_disagreement?: boolean;
}

export interface HistoricalEvaluationData {
  evaluation_name: string;
  seed_count: number;
  aggregate_economics: {
    mean_baseline_net_mxn: number;
    mean_smart_net_mxn: number;
    mean_improvement_pct: number;
    smart_win_rate_pct: number;
  };
  aggregate_operations: {
    mean_baseline_distance_km: number;
    mean_smart_distance_km: number;
    total_smart_safety_violations: number;
    total_baseline_safety_violations: number;
  };
}
