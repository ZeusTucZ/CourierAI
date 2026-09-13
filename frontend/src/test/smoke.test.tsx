import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SimpleHeader } from '../components/SimpleHeader';
import { OrdersFeed } from '../components/OrdersFeed';
import { SimpleShiftCompleteModal } from '../components/SimpleShiftCompleteModal';
import type { SimulationState, TimelineEventItem, DecisionInspectorData } from '../types';

const mockState: SimulationState = {
  sim_time: '18:42',
  sim_time_iso: '2026-03-21T18:42:00',
  shift_start: '15:00',
  shift_end: '23:00',
  status: 'running',
  seed: 30004,
  vehicle: 'moto',
  stream_hash: '4844898c6335',
  playback_speed: 5,
  current_shock: null,
  latest_shock_reaction: null,
  incoming_order: {
    order_id: 'ORD-0041',
    sim_time: '18:42',
    platform: 'rappi',
    zone_pickup: 7,
    zone_dropoff: 1,
    distance_pickup_km: 1.2,
    distance_delivery_km: 5.0,
    distance_total_km: 6.2,
    base_pay_mxn: 65.0,
    est_tip_mxn: 7.5,
    surge_multiplier: 1.0,
    restaurant_prep_min: 5.0,
    weight_kg: 2.0,
    baseline_decision: 'ACCEPT',
    smart_decision: 'SKIP',
    is_disagreement: true,
    agreement_summary: 'Baseline ACCEPT, Smart SKIP',
    smart_reason: 'Skipped because adjusted rate was $74/hr, below the $125/hr threshold.',
  },
  comparison: {
    leader: 'Smart',
    net_difference: 89.0,
    uplift_pct: 20.3,
    is_smart_winning: true,
  },
  baseline: {
    name: 'FirstNearbyOrderBaseline',
    net_earnings_mxn: 438.2,
    gross_earnings_mxn: 520.0,
    operating_costs_mxn: 81.8,
    current_zone: 7,
    status: 'delivering',
    orders_completed: 4,
    orders_accepted: 5,
    orders_skipped: 2,
    distance_traveled_km: 32.4,
    idle_time_min: 15.0,
    late_deliveries: 0,
    safety_violations: 0,
    mxn_per_hour: 118.0,
    mxn_per_km: 13.5,
    active_orders: [],
    last_decision: {
      decision: 'ACCEPT',
      reason: 'Within nearby-distance threshold',
      binding_constraint: null,
    },
  },
  smart: {
    name: 'SmartAgent',
    net_earnings_mxn: 527.1,
    gross_earnings_mxn: 610.0,
    operating_costs_mxn: 82.9,
    current_zone: 7,
    status: 'idle',
    orders_completed: 5,
    orders_accepted: 5,
    orders_skipped: 4,
    distance_traveled_km: 26.8,
    idle_time_min: 22.0,
    late_deliveries: 0,
    safety_violations: 0,
    reposition_distance_km: 1.5,
    reposition_count: 1,
    mxn_per_hour: 142.0,
    mxn_per_km: 19.6,
    active_orders: [],
    last_decision: {
      decision: 'SKIP',
      reason: 'Skipped because adjusted rate was $74/hr, below the $125/hr threshold.',
      binding_constraint: null,
      adjusted_rate_mxn_hr: 74.0,
      reservation_wage_mxn_hr: 125.0,
    },
  },
};

const mockEvents: TimelineEventItem[] = [
  {
    id: 1,
    sim_time: '18:42',
    sim_time_iso: '2026-03-21T18:42:00',
    type: 'order_decision',
    title: 'Order ORD-0041 Evaluated',
    description: 'Order ORD-0041: Baseline ACCEPT, Smart SKIP (Different decision)',
    level: 'warning',
    order_id: 'ORD-0041',
    is_disagreement: true,
  },
  {
    id: 2,
    sim_time: '18:50',
    sim_time_iso: '2026-03-21T18:50:00',
    type: 'shock',
    title: 'ROAD CLOSURE',
    description: 'Av. Constitución closed. Smart route recalculated (+0.17 km, +25 sec).',
    level: 'warning',
  },
];

const mockInspectorData: DecisionInspectorData = {
  order_id: 'ORD-0041',
  sim_time: '18:42',
  offer_details: {
    platform: 'rappi',
    zone_pickup: 7,
    zone_dropoff: 1,
    distance_pickup_km: 1.2,
    distance_delivery_km: 5.0,
    distance_total_km: 6.2,
    base_pay_mxn: 65.0,
    est_tip_mxn: 7.5,
    surge_multiplier: 1.0,
    restaurant_prep_min: 5.0,
    weight_kg: 2.0,
    volume_liters: 3.0,
  },
  baseline: {
    decision: 'ACCEPT',
    reason: 'Within nearby-distance threshold',
    binding_constraint: null,
    threshold_km: 15.0,
  },
  smart: {
    decision: 'SKIP',
    reason: 'Adjusted rate below reservation wage.',
    binding_constraint: null,
    economics: {
      gross_pay_mxn: 72.5,
      operating_cost_mxn: 21.2,
      net_pay_mxn: 51.3,
      raw_rate_mxn_hr: 75.07,
      adjusted_rate_mxn_hr: 75.07,
      reservation_wage_mxn_hr: 125.0,
      deadhead_km: 1.2,
      zone_value_mxn_hr: null,
      opportunity_cost_mxn: null,
      stacking_impact_min: null,
    },
    historical_signal: null,
  },
};

describe('MVP4 Frontend Smoke Tests', () => {
  it('renders header with seed, stream verification, and earnings comparison', () => {
    render(
      <SimpleHeader
        state={mockState}
        onStart={vi.fn()}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onReset={vi.fn()}
        onSpeedChange={vi.fn()}
        onInjectShock={vi.fn()}
        onOpenBenchmark={vi.fn()}
      />
    );

    expect(screen.getByText('Courier AI Simulator')).toBeDefined();
    expect(screen.getByText(/Same order stream/i)).toBeDefined();
    expect(screen.getByText(/Seed: 30004/i)).toBeDefined();
    expect(screen.getByText('$527')).toBeDefined(); // Smart earnings
    expect(screen.getByText('$438')).toBeDefined(); // Baseline earnings
    expect(screen.getByText('+$89')).toBeDefined(); // Spread
    expect(screen.getByText('+20.3%')).toBeDefined(); // Uplift
  });

  it('renders order feed showing same order, decisions, and disagreement', () => {
    render(
      <OrdersFeed
        events={mockEvents}
        onFetchDecisionInspector={vi.fn()}
      />
    );

    expect(screen.getByText('ORD-0041')).toBeDefined();
    expect(screen.getByText('Different decision')).toBeDefined();
    expect(screen.getByText('ROAD CLOSURE')).toBeDefined();
  });

  it('opens decision explanation in order card when clicking Why?', async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockInspectorData);

    render(
      <OrdersFeed
        events={mockEvents}
        onFetchDecisionInspector={fetchMock}
      />
    );

    const whyButton = screen.getByText('Why?');
    fireEvent.click(whyButton);

    expect(fetchMock).toHaveBeenCalledWith('ORD-0041');
    const reasonText = await screen.findByText(/Adjusted rate below reservation wage/i);
    expect(reasonText).toBeDefined();
    expect(screen.getByText('$125.00/hr')).toBeDefined();
  });

  it('renders shift completion modal with head-to-head metrics and held-out benchmark', () => {
    render(
      <SimpleShiftCompleteModal
        isOpen={true}
        state={mockState}
        onReset={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('SHIFT COMPLETE')).toBeDefined();
    expect(screen.getByText('SmartAgent')).toBeDefined();
    expect(screen.getByText(/Smart won by \+\$88.90 MXN/i)).toBeDefined();
    expect(screen.getByText(/Validated Offline Results/i)).toBeDefined();
    expect(screen.getByText('+17.12%')).toBeDefined();
  });
});
