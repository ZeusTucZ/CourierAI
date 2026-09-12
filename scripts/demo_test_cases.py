"""Readable, controlled MVP 2 demonstrations. Run: python -m scripts.demo_test_cases."""
from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.models.strategy import StrategySnapshot
from app.simulation.simulator import Simulator
from tests.mvp2_support import make_order, make_shift, make_shock, selected, stream


def banner(title):
    print("=" * 56)
    print(title)
    print("=" * 56)


def same_world_different_states():
    banner("CASE 3/4 — SAME ORDERS, DIFFERENT STATES")
    cfg = make_shift(start="2026-03-21T12:00:00")
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=100, zone_values={7: -1000})
    source = stream(cfg,
        make_order(cfg, at=0, order_id="ORD-001", zone_pickup=3, zone_dropoff=7,
                   distance_pickup_km=1, distance_delivery_km=4, base_pay_mxn=80, est_tip_mxn=0),
        make_order(cfg, at=8, order_id="ORD-002", zone_pickup=7, zone_dropoff=4,
                   distance_pickup_km=.5, distance_delivery_km=6, base_pay_mxn=120, est_tip_mxn=0))
    baseline = Simulator(cfg, GreedyRateBaseline(snapshot)).run(source)
    smart = Simulator(cfg, SmartAgent(snapshot)).run(source)
    b, s = selected(baseline, "decision"), selected(smart, "decision")
    assert selected(baseline, "order_offered") == selected(smart, "order_offered")
    assert baseline.state is not smart.state
    for left, right in zip(b, s):
        print(f"\n{left['sim_time'][11:16]} ORDER {left['order_id']}")
        for name, event in (("Baseline", left), ("Smart", right)):
            state = event["courier_state"]
            pending = event["decision_request"]["courier_state_overrides"]["in_flight_orders"]
            print(f"{name} before: in_flight={len(pending)}, weight={state['current_weight_kg']} kg, "
                  f"committed_time={sum(o['estimated_pickup_min'] + o['estimated_delivery_min'] + o['restaurant_prep_min'] for o in pending):.1f} min")
            print(f"  {event['decision']} ({event['binding_constraint'] or 'economic'}): {event['reason']}")
    assert (b[0]["decision"], s[0]["decision"]) == ("ACCEPT", "SKIP")
    assert len(b[1]["decision_request"]["courier_state_overrides"]["in_flight_orders"]) == 1
    assert not s[1]["decision_request"]["courier_state_overrides"]["in_flight_orders"]
    print("\nOrder identical for both: YES — PASS")


def delay_shock():
    banner("CASE 13 — DELAY SHOCK")
    cfg = make_shift()
    result = Simulator(cfg, SmartAgent()).run(stream(cfg,
        make_order(cfg, order_id="A", estimated_pickup_min=10, estimated_delivery_min=15),
        make_shock(cfg, 2, "delay", order_id="A", slip_min=15),
        make_order(cfg, at=3, order_id="B", zone_pickup=8, zone_dropoff=8)))
    before = next(e for e in selected(result, "position_update") if e.get("action") == "state_updated" and e["commitments"])
    after = next(e for e in selected(result, "position_update") if e["sim_time"].endswith("18:02:00") and e.get("action") == "state_updated")
    print("Before: A ETA 25 min")
    print("Shock: delay +15 min for A")
    print(f"After: A ETA {after['commitments'][0]['estimated_completion_time'][11:16]} (40 min from shift start)")
    print(f"B received direct delay: {'YES' if selected(result, 'order_offered')[1]['restaurant_prep_min'] else 'NO'}")
    assert before["commitments"][0]["estimated_completion_time"].endswith("18:25:00")
    assert after["commitments"][0]["estimated_completion_time"].endswith("18:40:00")
    print("PASS")


def earnings():
    banner("CASE 20 — EARNINGS")
    cfg = make_shift()
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=0, zone_values={})
    result = Simulator(cfg, SmartAgent(snapshot)).run(stream(cfg,
        make_order(cfg, order_id="A", base_pay_mxn=100, est_tip_mxn=0,
                   distance_pickup_km=5, distance_delivery_km=5),
        make_order(cfg, at=11, order_id="B", base_pay_mxn=70, est_tip_mxn=0,
                   distance_pickup_km=5, distance_delivery_km=10)))
    m = result.metrics
    print("Expected: gross=170.00 cost=30.00 net=140.00")
    print(f"Actual:   gross={m.gross_earnings_mxn:.2f} cost={m.operating_costs_mxn:.2f} net={m.net_earnings_mxn:.2f}")
    assert (m.gross_earnings_mxn, round(m.operating_costs_mxn, 2), round(m.net_earnings_mxn, 2)) == (170, 30, 140)
    print("PASS")


def main():
    same_world_different_states()
    delay_shock()
    earnings()


if __name__ == "__main__":
    main()
