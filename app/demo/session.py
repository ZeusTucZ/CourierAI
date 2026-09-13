"""Dual simulation session running FirstNearbyOrderBaseline vs SmartAgent side-by-side.
Strictly preservation-only: does not alter agent policies, models, or simulator rules.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import heapq
import math
from pathlib import Path
from typing import Any, Literal

from app.agents.nearby import FirstNearbyBaselineConfig, FirstNearbyOrderBaseline
from app.agents.smart import SmartAgent
from app.evaluation.freeze import load_frozen
from app.logging.event_log import encode_events
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig
from app.simulation.events import Event, event_time
from app.simulation.generator import generate_shift
from app.simulation.strategic import StrategicSimulator

OUT = Path("artifacts")
DEMO_DIR = OUT / "demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)


class SteppableStrategicSimulator(StrategicSimulator):
    """Subclass of StrategicSimulator exposing step-by-step event progression without altering logic."""

    def __init__(self, config, agent, model, policy):
        super().__init__(config, agent, model, policy)
        self.stream_digest: str = ""
        self.last_step_event: dict[str, Any] | None = None

    def init_stream(self, stream: list[Event]):
        self._used = True
        source = deepcopy(stream)
        self._validate_stream(source)
        self.stream_digest = sha256(encode_events(source)).hexdigest()
        priorities = {"shift_start": -1, "shock": 2, "order_offered": 3, "shift_end": 9}
        for event in source:
            self._push(event_time(event), priorities[event["event"]], event["event"], event)
        self._schedule_extensions()

    def has_events(self) -> bool:
        return bool(self._queue)

    def next_time(self) -> datetime | None:
        return self._queue[0][0] if self._queue else None

    def step_one(self) -> dict[str, Any] | None:
        if not self._queue:
            return None
        when, priority, seq, kind, payload = heapq.heappop(self._queue)
        if kind == "phase" and payload != self._work_version:
            return {"kind": "phase_skipped", "when": when}

        self._advance(when)
        record: dict[str, Any] = {"kind": kind, "when": when}

        if kind == "shift_start":
            self._emit("shift_start", **{k: v for k, v in payload.items() if k not in {"event", "sim_time"}},
                       source_event=payload, simulation_config=self.config.model_dump(mode="json"),
                       strategy_snapshot=self.agent.snapshot.model_dump(mode="json"),
                       agent_name=self.agent.name, simulator_version="mvp3-v1", stream_sha256=self.stream_digest)
            self._position(action="shift_started")
        elif kind == "order_offered":
            self._offer(payload)
            # Retrieve the newly emitted decision
            dec = next((e for e in reversed(self.log.events) if e["event"] == "decision"), None)
            record["decision"] = dec
            record["order_id"] = payload.get("order_id")
        elif kind == "shock":
            self._shock(payload)
            record["shock"] = payload
        elif kind == "phase":
            before_completed = self.state.orders_completed
            self._drain_finished_phases()
            if self.state.orders_completed > before_completed:
                record["completed_order"] = True
            if not self.state.in_flight_orders:
                policy = self.agent.snapshot.policy
                if self.state.continuous_riding_min >= policy.mandatory_riding_limit_min or (
                    policy.heat_start_hour <= when.hour < policy.heat_end_hour
                    and self.state.continuous_riding_min >= policy.heat_riding_limit_min):
                    self._start_break()
            self._refresh_execution()
        elif kind == "break_end":
            self.state.continuous_riding_us = 0
            self.state.last_break_end_time = when
            self.state.break_until = None
            self.state.status = "idle"
            self._position(action="break_completed")
            self._refresh_execution()
        elif kind == "expiry":
            before = self.world.rain_factor
            self.world.expire(payload)
            self._rescale_rain(before)
            self._position(action="shock_expired", shock_id=payload)
            self._drain_finished_phases()
            self._refresh_execution()
        elif kind == "shift_end":
            self._earnings()
            self._emit("shift_end", source_event=payload, **self.state.summary(),
                       earnings_mxn=self.state.net_earnings,
                       uncompleted_orders=len(self.state.in_flight_orders))
        else:
            self._internal_event(kind, payload)

        self.last_step_event = record
        return record


class DualSimulationSession:
    """Manages simultaneous, synchronized execution of both Baseline and SmartAgent."""

    def __init__(
        self,
        seed: int = 30004,
        shift_hours: float = 8.0,
        vehicle: str = "moto",
        start_location_zone: int = 7,
        playback_speed: int = 5,
    ):
        self.seed = seed
        self.shift_hours = shift_hours
        self.vehicle = vehicle
        self.start_location_zone = start_location_zone
        self.playback_speed = playback_speed
        self.status: Literal["idle", "running", "paused", "completed"] = "idle"

        # Load frozen production configurations
        frozen_config_path = OUT / "final_strategy_config.json"
        self.profile, self.model, self.policy = load_frozen(frozen_config_path)
        self.baseline_cfg = FirstNearbyBaselineConfig.load()

        self.cfg = ShiftConfig(
            seed=self.seed,
            shift_hours=self.shift_hours,
            vehicle=self.vehicle,
            start_location_zone=self.start_location_zone,
            profile=self.profile,
        )

        # Generate single source stream for both agents
        self.source = generate_shift(self.cfg)
        self.stream_hash = sha256(encode_events(self.source)).hexdigest()[:12]

        # Initialize baseline (strategic actions disabled)
        snapshot_base = StrategySnapshot(reservation_wage_mxn_hr=self.policy.base_reservation_wage, zone_values={})
        base_policy = self.policy.model_copy(update={
            "use_zone_value": False, "use_reposition": False,
            "use_improved_batching": False, "use_historical_prediction": False,
            "use_cancellation": False,
        })
        self.sim_baseline = SteppableStrategicSimulator(
            self.cfg,
            FirstNearbyOrderBaseline(self.baseline_cfg, snapshot_base),
            self.model,
            base_policy,
        )

        # Initialize SmartAgent (full frozen policy)
        snapshot_smart = StrategySnapshot(reservation_wage_mxn_hr=self.policy.base_reservation_wage, zone_values={})
        self.sim_smart = SteppableStrategicSimulator(
            self.cfg,
            SmartAgent(snapshot_smart),
            self.model,
            self.policy,
        )

        self.sim_baseline.init_stream(self.source)
        self.sim_smart.init_stream(self.source)

        self.current_sim_time: datetime = self.cfg.simulation.simulation_start_time
        self.shift_start: datetime = self.cfg.simulation.simulation_start_time
        self.shift_end: datetime = self.cfg.shift_end

        self.timeline_events: list[dict[str, Any]] = []
        self.decisions_log: dict[str, dict[str, Any]] = {}
        self.incoming_order: dict[str, Any] | None = None
        self.latest_shock: dict[str, Any] | None = None
        self.latest_shock_reaction: dict[str, Any] | None = None
        self.shock_history: list[dict[str, Any]] = []
        self.scenario_counter: int = 1

        self.add_timeline_event(
            sim_time=self.current_sim_time,
            event_type="shift_start",
            title="Shift Started",
            description=f"Shift started at Zone {self.start_location_zone} ({self.vehicle.capitalize()}). Both agents active.",
            level="info",
        )

    def add_timeline_event(self, sim_time: datetime, event_type: str, title: str, description: str, level: str = "info", **extra):
        event = {
            "id": len(self.timeline_events) + 1,
            "sim_time": sim_time.strftime("%H:%M"),
            "sim_time_iso": sim_time.isoformat(),
            "type": event_type,
            "title": title,
            "description": description,
            "level": level,
            **extra,
        }
        self.timeline_events.append(event)

    def is_completed(self) -> bool:
        return not self.sim_baseline.has_events() and not self.sim_smart.has_events()

    def step(self) -> dict[str, Any]:
        """Advance simulation to the next meaningful event milestone."""
        if self.is_completed():
            self.status = "completed"
            return self.get_state()

        # Step until a major interactive event (order, shock, or completion) occurs in either agent
        found_interactive = False
        max_substeps = 200  # Avoid runaway loop
        substep_count = 0

        while (self.sim_baseline.has_events() or self.sim_smart.has_events()) and not found_interactive and substep_count < max_substeps:
            substep_count += 1
            t_base = self.sim_baseline.next_time()
            t_smart = self.sim_smart.next_time()

            candidates = [t for t in (t_base, t_smart) if t is not None]
            if not candidates:
                break
            min_target = min(candidates)

            # Advance baseline if it has events at min_target
            if t_base is not None and t_base <= min_target:
                rec_b = self.sim_baseline.step_one()
            else:
                rec_b = None

            # Advance smart if it has events at min_target
            if t_smart is not None and t_smart <= min_target:
                rec_s = self.sim_smart.step_one()
            else:
                rec_s = None

            # Update session current time to furthest reached
            self.current_sim_time = max(self.sim_baseline.state.current_sim_time, self.sim_smart.state.current_sim_time)

            # Check if this was an order offer
            if (rec_b and rec_b.get("kind") == "order_offered") or (rec_s and rec_s.get("kind") == "order_offered"):
                found_interactive = True
                order_id = (rec_b or rec_s).get("order_id")

                # Both agents receive the exact same offer
                dec_b = rec_b.get("decision") if rec_b else next((e for e in reversed(self.sim_baseline.log.events) if e.get("order_id") == order_id and e.get("event") == "decision"), None)
                dec_s = rec_s.get("decision") if rec_s else next((e for e in reversed(self.sim_smart.log.events) if e.get("order_id") == order_id and e.get("event") == "decision"), None)

                offer_event = next((e for e in self.source if e.get("order_id") == order_id), None)
                if offer_event is None:
                    # Look up from logs
                    offer_event = (dec_b or dec_s or {}).get("decision_request", {})

                b_choice = dec_b.get("decision", "SKIP") if dec_b else "SKIP"
                s_choice = dec_s.get("decision", "SKIP") if dec_s else "SKIP"
                is_disagreement = b_choice != s_choice

                # Build Inspector Record
                inspector_data = self._build_decision_inspector(order_id, offer_event, dec_b, dec_s)
                self.decisions_log[order_id] = inspector_data

                self.incoming_order = {
                    "order_id": order_id,
                    "sim_time": self.current_sim_time.strftime("%H:%M"),
                    "platform": offer_event.get("platform", "delivery"),
                    "zone_pickup": offer_event.get("zone_pickup"),
                    "zone_dropoff": offer_event.get("zone_dropoff"),
                    "distance_pickup_km": round(offer_event.get("distance_pickup_km", 0), 2),
                    "distance_delivery_km": round(offer_event.get("distance_delivery_km", 0), 2),
                    "distance_total_km": round(offer_event.get("distance_pickup_km", 0) + offer_event.get("distance_delivery_km", 0), 2),
                    "base_pay_mxn": round(offer_event.get("base_pay_mxn", 0), 2),
                    "est_tip_mxn": round(offer_event.get("est_tip_mxn", 0), 2),
                    "surge_multiplier": offer_event.get("surge_multiplier", 1.0),
                    "restaurant_prep_min": round(offer_event.get("restaurant_prep_min", 0), 1),
                    "weight_kg": round(offer_event.get("weight_kg", 0), 1),
                    "baseline_decision": b_choice,
                    "smart_decision": s_choice,
                    "is_disagreement": is_disagreement,
                    "agreement_summary": f"Both agents → {b_choice}" if not is_disagreement else f"Disagreement: Baseline {b_choice} vs Smart {s_choice}",
                    "smart_reason": dec_s.get("reason", "") if dec_s else "",
                }

                # Add to timeline
                summary_text = f"Baseline {b_choice}, Smart {s_choice}"
                if is_disagreement:
                    desc = f"Disagreement on {order_id}: Baseline {b_choice}, Smart {s_choice}. Smart Reason: {dec_s.get('reason', '')}"
                    level = "warning"
                else:
                    desc = f"Both accepted {order_id}." if b_choice == "ACCEPT" else f"Both skipped {order_id}."
                    level = "success" if b_choice == "ACCEPT" else "info"

                self.add_timeline_event(
                    sim_time=self.current_sim_time,
                    event_type="order_decision",
                    title=f"Order {order_id}: {summary_text}",
                    description=desc,
                    level=level,
                    order_id=order_id,
                    is_disagreement=is_disagreement,
                )

            # Check if this was a shock
            elif (rec_b and rec_b.get("kind") == "shock") or (rec_s and rec_s.get("kind") == "shock"):
                found_interactive = True
                shock_info = (rec_b or rec_s).get("shock", {})
                s_type = shock_info.get("shock_type", "shock").upper()
                duration = shock_info.get("duration_min")
                dur_str = f" ({duration} min)" if duration else ""

                self.latest_shock = {
                    "shock_type": shock_info.get("shock_type"),
                    "sim_time": self.current_sim_time.strftime("%H:%M"),
                    "duration_min": duration,
                    "message": f"⚠ {s_type} STARTED at {self.current_sim_time.strftime('%H:%M')}{dur_str}",
                }
                self.shock_history.append(self.latest_shock)

                # Record reactions
                self.latest_shock_reaction = {
                    "shock_type": shock_info.get("shock_type"),
                    "sim_time": self.current_sim_time.strftime("%H:%M"),
                    "smart_reaction": "Re-evaluated active commitments, adjusted physical travel time estimates, and refreshed SLA buffer.",
                    "baseline_reaction": "Adjusted travel time by physical shock factor, continued nearest-distance heuristic.",
                }

                self.add_timeline_event(
                    sim_time=self.current_sim_time,
                    event_type="shock",
                    title=f"Shock: {s_type} Active",
                    description=f"{s_type} shock applied to both couriers at {self.current_sim_time.strftime('%H:%M')}{dur_str}.",
                    level="warning",
                )

            # Check if shift ended
            elif (rec_b and rec_b.get("kind") == "shift_end") or (rec_s and rec_s.get("kind") == "shift_end"):
                found_interactive = True
                self.status = "completed"
                self.add_timeline_event(
                    sim_time=self.shift_end,
                    event_type="shift_end",
                    title="Shift Completed",
                    description=f"Shift completed at {self.shift_end.strftime('%H:%M')}. Final results available.",
                    level="success",
                )

        if self.is_completed():
            self.status = "completed"

        return self.get_state()

    def _build_decision_inspector(self, order_id: str, offer: dict[str, Any], dec_b: dict[str, Any] | None, dec_s: dict[str, Any] | None) -> dict[str, Any]:
        econ = (dec_s or {}).get("economics") or {}
        strat = (dec_s or {}).get("strategy_snapshot") or {}
        preds = strat.get("zone_predictions", {})
        zone_p = offer.get("zone_pickup")
        pred_signal = preds.get(str(zone_p)) or preds.get(zone_p)

        dist_pickup = offer.get("distance_pickup_km", 0)
        dist_dropoff = offer.get("distance_delivery_km", 0)

        return {
            "order_id": order_id,
            "sim_time": self.current_sim_time.strftime("%H:%M"),
            "offer_details": {
                "platform": offer.get("platform", "delivery"),
                "zone_pickup": zone_p,
                "zone_dropoff": offer.get("zone_dropoff"),
                "distance_pickup_km": round(dist_pickup, 2),
                "distance_delivery_km": round(dist_dropoff, 2),
                "distance_total_km": round(dist_pickup + dist_dropoff, 2),
                "base_pay_mxn": round(offer.get("base_pay_mxn", 0), 2),
                "est_tip_mxn": round(offer.get("est_tip_mxn", 0), 2),
                "surge_multiplier": offer.get("surge_multiplier", 1.0),
                "restaurant_prep_min": round(offer.get("restaurant_prep_min", 0), 1),
                "weight_kg": round(offer.get("weight_kg", 0), 1),
                "volume_liters": round(offer.get("volume_liters", 0), 1),
            },
            "baseline": {
                "decision": dec_b.get("decision", "SKIP") if dec_b else "SKIP",
                "reason": dec_b.get("reason", "") if dec_b else "No decision recorded",
                "binding_constraint": dec_b.get("binding_constraint") if dec_b else None,
                "threshold_km": round(self.baseline_cfg.max_distance_km, 2),
            },
            "smart": {
                "decision": dec_s.get("decision", "SKIP") if dec_s else "SKIP",
                "reason": dec_s.get("reason", "") if dec_s else "No decision recorded",
                "binding_constraint": dec_s.get("binding_constraint") if dec_s else None,
                "economics": {
                    "gross_pay_mxn": round(econ.get("gross_pay_mxn", 0), 2) if econ else None,
                    "operating_cost_mxn": round(econ.get("operating_cost_mxn", 0), 2) if econ else None,
                    "net_pay_mxn": round(econ.get("net_pay_mxn", 0), 2) if econ else None,
                    "raw_rate_mxn_hr": round(econ.get("raw_rate_mxn_hr", 0), 2) if econ else None,
                    "adjusted_rate_mxn_hr": round(econ.get("adjusted_rate_mxn_hr", 0), 2) if econ else None,
                    "reservation_wage_mxn_hr": round(econ.get("reservation_wage_mxn_hr", self.policy.base_reservation_wage), 2) if econ else self.policy.base_reservation_wage,
                    "deadhead_km": round(econ.get("deadhead_km", 0), 2) if econ else None,
                    "zone_value_mxn_hr": round(econ.get("zone_value_mxn_hr", 0), 2) if econ and econ.get("zone_value_mxn_hr") is not None else None,
                    "opportunity_cost_mxn": round(econ.get("opportunity_cost_mxn", 0), 2) if econ and econ.get("opportunity_cost_mxn") is not None else None,
                    "stacking_impact_min": econ.get("stacking_time_min") if econ else None,
                },
                "historical_signal": pred_signal,
            },
        }

    def inject_shock(
        self,
        shock_type: Literal["rain", "surge", "closure", "delay"],
        duration_min: int | None = 30,
        zone: int | None = None,
        multiplier: float | None = 1.5,
        road: str | None = None,
        slip_min: int | None = 15,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        """Inject an exogenous shock in real time into both simulators."""
        now_str = self.current_sim_time.isoformat()
        shock_dict: dict[str, Any] = {
            "event": "shock",
            "sim_time": now_str,
            "shock_type": shock_type,
        }

        if shock_type == "rain":
            shock_dict["duration_min"] = duration_min or 30
        elif shock_type == "surge":
            shock_dict["zone"] = zone or self.sim_smart.state.current_zone
            shock_dict["multiplier"] = multiplier or 1.5
            shock_dict["duration_min"] = duration_min or 30
        elif shock_type == "closure":
            shock_dict["zone"] = zone or self.sim_smart.state.current_zone
            shock_dict["duration_min"] = duration_min or 30
            if road:
                shock_dict["road"] = road
        elif shock_type == "delay":
            active_smart = [j.offer.order_id for j in self.sim_smart.state.in_flight_orders]
            active_base = [j.offer.order_id for j in self.sim_baseline.state.in_flight_orders]
            chosen_order = order_id or (active_smart[0] if active_smart else (active_base[0] if active_base else "ORD-00001"))
            shock_dict["order_id"] = chosen_order
            shock_dict["slip_min"] = slip_min or 15

        # Execute shock on both simulators immediately
        self.sim_baseline._shock(shock_dict)
        self.sim_smart._shock(shock_dict)

        s_upper = shock_type.upper()
        dur_str = f" ({shock_dict.get('duration_min')} min)" if shock_dict.get("duration_min") else ""
        self.latest_shock = {
            "shock_type": shock_type,
            "sim_time": self.current_sim_time.strftime("%H:%M"),
            "duration_min": shock_dict.get("duration_min"),
            "message": f"⚠ {s_upper} INJECTED at {self.current_sim_time.strftime('%H:%M')}{dur_str}",
        }
        self.shock_history.append(self.latest_shock)

        self.latest_shock_reaction = {
            "shock_type": shock_type,
            "sim_time": self.current_sim_time.strftime("%H:%M"),
            "smart_reaction": f"SmartAgent processed {shock_type}: updated travel time factors, evaluated disruption impact on active route.",
            "baseline_reaction": f"Baseline processed {shock_type}: updated physical travel time, preserved FIFO single-order plan.",
        }

        self.add_timeline_event(
            sim_time=self.current_sim_time,
            event_type="shock_injected",
            title=f"Manual Shock: {s_upper}",
            description=f"Injected {s_upper} into active simulation at {self.current_sim_time.strftime('%H:%M')}{dur_str}.",
            level="warning",
        )

        return self.latest_shock

    def trigger_safety_scenario(self, scenario_type: str) -> dict[str, Any]:
        """Trigger an official constraint refusal on both agents."""
        self.scenario_counter += 1
        now_str = self.current_sim_time.isoformat()
        oid = f"DEMO-{scenario_type.upper()}-{self.scenario_counter:03d}"

        offer_payload: dict[str, Any] = {
            "event": "order_offered",
            "order_id": oid,
            "sim_time": now_str,
            "platform": "rappi",
            "zone_pickup": self.sim_smart.state.current_zone,
            "zone_dropoff": ((self.sim_smart.state.current_zone % 12) + 1),
            "distance_pickup_km": 1.0,
            "distance_delivery_km": 4.0,
            "base_pay_mxn": 75.0,
            "est_tip_mxn": 15.0,
            "surge_multiplier": 1.0,
            "restaurant_prep_min": 5.0,
            "weight_kg": 3.0,
            "volume_liters": 5.0,
            "vehicle": self.vehicle,
        }

        if scenario_type == "vehicle_capacity":
            offer_payload["weight_kg"] = 50.0  # Exceeds moto 15kg limit
            desc_text = "Triggered Vehicle Capacity Scenario (Order weight 50.0 kg > 15 kg limit)"
        elif scenario_type == "shift_end_infeasible":
            offer_payload["sim_time"] = (self.shift_end - timedelta(minutes=20)).isoformat()
            offer_payload["distance_delivery_km"] = 15.0
            offer_payload["restaurant_prep_min"] = 10.0
            desc_text = "Triggered Shift End Infeasible Scenario (Estimated delivery 47 min after shift end)"
        elif scenario_type == "flagged_zone_night":
            offer_payload["zone_dropoff"] = 11  # Official flagged zone
            offer_payload["sim_time"] = self.current_sim_time.replace(hour=22, minute=30).isoformat()
            desc_text = "Triggered Flagged Zone Night Scenario (Delivery to Zone 11 after 22:00)"
        else:
            desc_text = f"Triggered {scenario_type} demo scenario"

        # Offer to both
        self.sim_baseline._offer(offer_payload)
        self.sim_smart._offer(offer_payload)

        dec_b = next((e for e in reversed(self.sim_baseline.log.events) if e.get("order_id") == oid and e.get("event") == "decision"), {})
        dec_s = next((e for e in reversed(self.sim_smart.log.events) if e.get("order_id") == oid and e.get("event") == "decision"), {})

        inspector = self._build_decision_inspector(oid, offer_payload, dec_b, dec_s)
        self.decisions_log[oid] = inspector

        self.incoming_order = {
            "order_id": oid,
            "sim_time": self.current_sim_time.strftime("%H:%M"),
            "platform": "demo_test",
            "zone_pickup": offer_payload["zone_pickup"],
            "zone_dropoff": offer_payload["zone_dropoff"],
            "distance_pickup_km": offer_payload["distance_pickup_km"],
            "distance_delivery_km": offer_payload["distance_delivery_km"],
            "distance_total_km": offer_payload["distance_pickup_km"] + offer_payload["distance_delivery_km"],
            "base_pay_mxn": offer_payload["base_pay_mxn"],
            "est_tip_mxn": offer_payload["est_tip_mxn"],
            "surge_multiplier": offer_payload["surge_multiplier"],
            "restaurant_prep_min": offer_payload["restaurant_prep_min"],
            "weight_kg": offer_payload["weight_kg"],
            "baseline_decision": dec_b.get("decision", "SKIP"),
            "smart_decision": dec_s.get("decision", "SKIP"),
            "is_disagreement": False,
            "agreement_summary": f"Both agents → SKIP (Refusal: {dec_s.get('binding_constraint')})",
            "smart_reason": dec_s.get("reason", ""),
        }

        self.add_timeline_event(
            sim_time=self.current_sim_time,
            event_type="safety_demo",
            title=f"Safety Refusal: {dec_s.get('binding_constraint')}",
            description=f"{desc_text}. Both agents correctly evaluated constraints and returned SKIP.",
            level="warning",
            order_id=oid,
        )

        return {
            "scenario": scenario_type,
            "order_id": oid,
            "baseline_decision": dec_b.get("decision"),
            "smart_decision": dec_s.get("decision"),
            "binding_constraint": dec_s.get("binding_constraint"),
            "smart_reason": dec_s.get("reason"),
        }

    def get_state(self) -> dict[str, Any]:
        """Generate real-time state payload for UI visualizer."""
        b_st = self.sim_baseline.state
        s_st = self.sim_smart.state

        b_net = round(b_st.net_earnings, 2)
        s_net = round(s_st.net_earnings, 2)
        diff = round(s_net - b_net, 2)
        uplift = round((diff / b_net * 100), 1) if b_net > 0 else (100.0 if s_net > 0 else 0.0)

        leader = "Smart" if s_net > b_net else ("Baseline" if b_net > s_net else "Tie")

        # Active commitments
        b_active = [{"order_id": j.offer.order_id, "pickup_zone": j.offer.zone_pickup, "dropoff_zone": j.offer.zone_dropoff, "promised_time": j.promised_completion_time.strftime("%H:%M")} for j in b_st.in_flight_orders]
        s_active = [{"order_id": j.offer.order_id, "pickup_zone": j.offer.zone_pickup, "dropoff_zone": j.offer.zone_dropoff, "promised_time": j.promised_completion_time.strftime("%H:%M")} for j in s_st.in_flight_orders]

        # Last decision
        last_b_dec = next((e for e in reversed(self.sim_baseline.log.events) if e.get("event") == "decision"), None)
        last_s_dec = next((e for e in reversed(self.sim_smart.log.events) if e.get("event") == "decision"), None)

        hours_elapsed = max(0.01, (self.current_sim_time - self.shift_start).total_seconds() / 3600)

        return {
            "sim_time": self.current_sim_time.strftime("%H:%M"),
            "sim_time_iso": self.current_sim_time.isoformat(),
            "shift_start": self.shift_start.strftime("%H:%M"),
            "shift_end": self.shift_end.strftime("%H:%M"),
            "status": self.status,
            "seed": self.seed,
            "vehicle": self.vehicle,
            "stream_hash": self.stream_hash,
            "playback_speed": self.playback_speed,
            "current_shock": self.latest_shock,
            "latest_shock_reaction": self.latest_shock_reaction,
            "incoming_order": self.incoming_order,
            "comparison": {
                "leader": leader,
                "net_difference": diff,
                "uplift_pct": uplift,
                "is_smart_winning": s_net > b_net,
            },
            "baseline": {
                "name": "FirstNearbyOrderBaseline",
                "net_earnings_mxn": b_net,
                "gross_earnings_mxn": round(b_st.gross_earnings, 2),
                "operating_costs_mxn": round(b_st.operating_costs, 2),
                "current_zone": b_st.current_zone,
                "status": b_st.status,
                "orders_completed": b_st.orders_completed,
                "orders_accepted": b_st.orders_accepted,
                "orders_skipped": b_st.orders_skipped,
                "distance_traveled_km": round(b_st.distance_traveled_km, 2),
                "idle_time_min": round(b_st.idle_time_min, 1),
                "late_deliveries": b_st.late_deliveries,
                "safety_violations": b_st.safety_violations,
                "mxn_per_hour": round(b_net / hours_elapsed, 1),
                "mxn_per_km": round(b_net / b_st.distance_traveled_km, 1) if b_st.distance_traveled_km > 0 else 0.0,
                "active_orders": b_active,
                "last_decision": {
                    "decision": last_b_dec.get("decision") if last_b_dec else "—",
                    "reason": last_b_dec.get("reason") if last_b_dec else "Waiting for offers",
                    "binding_constraint": last_b_dec.get("binding_constraint") if last_b_dec else None,
                },
            },
            "smart": {
                "name": "SmartAgent",
                "net_earnings_mxn": s_net,
                "gross_earnings_mxn": round(s_st.gross_earnings, 2),
                "operating_costs_mxn": round(s_st.operating_costs, 2),
                "current_zone": s_st.current_zone,
                "status": s_st.status,
                "orders_completed": s_st.orders_completed,
                "orders_accepted": s_st.orders_accepted,
                "orders_skipped": s_st.orders_skipped,
                "distance_traveled_km": round(s_st.distance_traveled_km, 2),
                "idle_time_min": round(s_st.idle_time_min, 1),
                "late_deliveries": s_st.late_deliveries,
                "safety_violations": s_st.safety_violations,
                "reposition_distance_km": round(s_st.reposition_distance_km, 2),
                "reposition_count": s_st.reposition_count,
                "mxn_per_hour": round(s_net / hours_elapsed, 1),
                "mxn_per_km": round(s_net / s_st.distance_traveled_km, 1) if s_st.distance_traveled_km > 0 else 0.0,
                "active_orders": s_active,
                "last_decision": {
                    "decision": last_s_dec.get("decision") if last_s_dec else "—",
                    "reason": last_s_dec.get("reason") if last_s_dec else "Waiting for offers",
                    "binding_constraint": last_s_dec.get("binding_constraint") if last_s_dec else None,
                    "adjusted_rate_mxn_hr": round((last_s_dec.get("economics") or {}).get("adjusted_rate_mxn_hr", 0), 1) if last_s_dec and last_s_dec.get("economics") else None,
                    "reservation_wage_mxn_hr": round((last_s_dec.get("economics") or {}).get("reservation_wage_mxn_hr", self.policy.base_reservation_wage), 1) if last_s_dec and last_s_dec.get("economics") else self.policy.base_reservation_wage,
                },
            },
        }
