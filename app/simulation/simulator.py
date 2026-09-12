"""Serial discrete-event execution, with independently owned courier/world state."""
import heapq
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256

from app.agents.base import Agent, decision_request
from app.decision.constraints import evaluate_constraints
from app.decision.timing import WorkPlan, build_work_plan
from app.logging.event_log import EventLog, encode_events
from app.metrics.collector import collect_metrics
from app.metrics.results import ShiftResult
from app.models.requests import DecideRequest
from app.models.state import resolve_state
from app.simulation.config import ShiftConfig
from app.simulation.events import Event, Shock, event_time
from app.simulation.shocks import WorldState, apply_shock
from app.simulation.state import ActiveOrder, CourierState, MINUTE_US, to_us


class Simulator:
    def __init__(self, config: ShiftConfig, agent: Agent):
        self.config, self.agent = config, agent
        self.state = CourierState.for_shift(config)
        self.world = WorldState(config.simulation)
        self.log = EventLog()
        self._queue = []
        self._sequence = 0
        self._work_version = 0
        self._used = False

    def _push(self, when: datetime, priority: int, kind: str, payload=None):
        if when <= self.state.shift_end:
            heapq.heappush(self._queue, (when, priority, self._sequence, kind, payload))
            self._sequence += 1

    def _emit(self, name: str, **fields):
        self.log.append({"event": name, "sim_time": self.state.current_sim_time.isoformat(), **fields})

    def _position(self, **fields):
        self._emit("position_update", zone=self.state.current_zone, status=self.state.status,
                   continuous_riding_min=self.state.continuous_riding_min,
                   current_weight_kg=self.state.current_weight_kg,
                   current_volume_liters=self.state.current_volume_liters,
                   commitments=[{"order_id": job.offer.order_id,
                                 "promised_completion_time": job.promised_completion_time.isoformat(),
                                 "estimated_completion_time": job.estimated_completion_time.isoformat()}
                                for job in self.state.in_flight_orders], **fields)

    def _earnings(self, **fields):
        state = self.state
        self._emit("earnings_update", earnings_mxn=state.net_earnings,
                   gross_earnings_mxn=state.gross_earnings, operating_costs_mxn=state.operating_costs,
                   orders_completed=state.orders_completed, distance_traveled_km=state.distance_traveled_km,
                   idle_time_min=state.idle_time_min, late_deliveries=state.late_deliveries,
                   safety_violations=state.safety_violations, **fields)

    def _invariant(self, condition: bool, name: str):
        if not condition:
            self.state.safety_violations += 1
            raise RuntimeError(f"Execution safety invariant failed: {name}")

    def _advance(self, when: datetime):
        state = self.state
        elapsed = round((when - state.current_sim_time).total_seconds() * 1_000_000)
        self._invariant(elapsed >= 0 and when <= state.shift_end, "chronology / shift end")
        if state.in_flight_orders and not state.execution_hold:
            phase = state.in_flight_orders[0].phases[0]
            self._invariant(elapsed <= phase.remaining_us, "phase scheduling")
            if phase.kind != "waiting":
                policy = self.agent.snapshot.policy
                self._invariant(state.continuous_riding_us + elapsed <= to_us(policy.mandatory_riding_limit_min), "mandatory_break")
                day = state.current_sim_time.replace(hour=0, minute=0, second=0, microsecond=0)
                while day < when:
                    begin = day + timedelta(hours=policy.heat_start_hour)
                    end = day + timedelta(hours=policy.heat_end_hour)
                    if state.current_sim_time < end and when > begin:
                        heat_us = round((min(when, end) - state.current_sim_time).total_seconds() * 1_000_000)
                        self._invariant(state.continuous_riding_us + heat_us <= to_us(policy.heat_riding_limit_min), "heat_rule")
                    day += timedelta(days=1)
                traveled = (phase.distance_km if elapsed == phase.remaining_us
                            else phase.distance_km * (elapsed / phase.remaining_us)) if phase.remaining_us else 0
                phase.distance_km -= traveled
                state.distance_traveled_km += traveled
                state.operating_costs += traveled * self.agent.snapshot.vehicle_profiles[state.vehicle].operating_cost_mxn_per_km
                state.continuous_riding_us += elapsed
            phase.remaining_us -= elapsed
        elif state.status == "idle":
            state.idle_time_us += elapsed
        state.current_sim_time = when

    def _drain_finished_phases(self):
        state = self.state
        while state.in_flight_orders and not state.execution_hold:
            job = state.in_flight_orders[0]
            if job.phases and job.phases[0].remaining_us:
                break
            if job.phases:
                phase = job.phases.pop(0)
                # An explicit zero-time travel estimate still incurs its quoted
                # distance cost; ordinary completed phases have no residual distance.
                if phase.distance_km:
                    state.distance_traveled_km += phase.distance_km
                    state.operating_costs += phase.distance_km * self.agent.snapshot.vehicle_profiles[state.vehicle].operating_cost_mxn_per_km
                state.status = job.phases[0].kind if job.phases else "idle"
                if phase.kind == "to_pickup":
                    state.current_zone = job.offer.zone_pickup
                    self._position(order_id=job.offer.order_id, action="pickup_arrival")
                elif phase.kind == "to_dropoff":
                    self._invariant(not (job.offer.zone_dropoff in self.agent.snapshot.flagged_zones
                                         and state.current_sim_time.hour >= self.agent.snapshot.policy.night_start_hour), "flagged_zone_night")
                    state.current_zone = job.offer.zone_dropoff
                    self._position(order_id=job.offer.order_id, action="dropoff_arrival")
            if not job.phases:
                state.in_flight_orders.pop(0)
                state.gross_earnings += job.offer.base_pay_mxn * job.offer.surge_multiplier + job.offer.est_tip_mxn
                state.orders_completed += 1
                late = state.current_sim_time > job.promised_completion_time
                state.late_deliveries += int(late)
                self._earnings(completed_order_id=job.offer.order_id, late=late,
                               promised_completion_time=job.promised_completion_time.isoformat())

    def _remaining_violation(self):
        state = self.state
        if not state.in_flight_orders:
            return None
        # Reuse the official constraint functions on the actual remaining route,
        # with the last queued job as the candidate and predecessors in-flight.
        last = state.in_flight_orders[-1]
        remaining = last.remaining()
        overrides = state.overrides().model_copy(update={
            "in_flight_orders": tuple(job.remaining() for job in state.in_flight_orders[:-1])})
        request = DecideRequest.model_validate({**last.offer.model_dump(),
            **remaining.model_dump(exclude={"order_id"}), "sim_time": state.current_sim_time,
            "courier_state_overrides": overrides})
        resolved = resolve_state(request.sim_time, overrides, self.agent.snapshot.policy.default_shift_hours)
        cursor = state.current_sim_time
        riding_us = 0
        intervals, dropoffs = [], []
        for job in state.in_flight_orders:
            for phase in job.phases:
                end = cursor + timedelta(microseconds=phase.remaining_us)
                if phase.kind != "waiting" and phase.remaining_us:
                    intervals.append((cursor, end))
                    riding_us += phase.remaining_us
                cursor = end
            dropoffs.append((job.offer.zone_dropoff, cursor))
        total = (cursor - state.current_sim_time).total_seconds() / 60
        plan = WorkPlan(total, sum(p.remaining_us for p in last.phases) / MINUTE_US,
                        riding_us / MINUTE_US, cursor, tuple(intervals), tuple(dropoffs), False)
        return evaluate_constraints(request, resolved, self.agent.snapshot, plan)

    def _refresh_execution(self):
        state = self.state
        state.recompute_completions()
        violation = self._remaining_violation()
        previous = state.execution_hold
        state.execution_hold = violation.constraint if violation else None
        if violation and previous != violation.constraint:
            state.post_accept_infeasible += 1
            state.status = "waiting"
            self._position(action="post_accept_infeasible", binding_constraint=violation.constraint,
                           reason=violation.reason, pending_order_ids=[job.offer.order_id for job in state.in_flight_orders])
        elif previous and not violation:
            self._position(action="execution_resumed")
        self._work_version += 1
        if state.execution_hold:
            state.status = "waiting"
        elif state.in_flight_orders:
            state.status = state.in_flight_orders[0].phases[0].kind
            remaining = state.in_flight_orders[0].phases[0].remaining_us
            self._push(state.current_sim_time + timedelta(microseconds=remaining), 0, "phase", self._work_version)
        elif state.break_until:
            state.status = "on_break"
        else:
            state.status = "idle"
        self._position(action="state_updated")

    def _start_break(self):
        state = self.state
        if state.in_flight_orders or state.break_until or state.continuous_riding_us == 0:
            return
        state.break_until = state.current_sim_time + timedelta(minutes=self.agent.snapshot.policy.mandatory_break_min)
        state.status = "on_break"
        self._push(state.break_until, 0, "break_end")
        self._position(action="break_started", break_end_time=state.break_until.isoformat())

    def _offer(self, source: Event):
        state = self.state
        order = self.world.prepare_offer(source, self.agent.snapshot)
        self._emit("order_offered", **order.model_dump(mode="json", exclude={"event", "sim_time", "courier_state_overrides"}, exclude_none=True),
                   source_event=source)
        request = decision_request(order, state)
        state.orders_offered += 1
        response = self.agent.decide(order, state)
        self._emit("decision", **response.model_dump(mode="json"), decision_request=request.model_dump(mode="json"),
                   courier_state=state.summary())
        if response.decision == "ACCEPT":
            resolved = resolve_state(order.sim_time, request.courier_state_overrides,
                                     self.agent.snapshot.policy.default_shift_hours)
            plan = build_work_plan(request, resolved, self.agent.snapshot)
            self._invariant(evaluate_constraints(request, resolved, self.agent.snapshot, plan) is None, "agent accepted infeasible offer")
            state.in_flight_orders.append(ActiveOrder.accepted(order, self.agent.snapshot, plan.completion_time))
            state.orders_accepted += 1
            profile = self.agent.snapshot.vehicle_profiles[state.vehicle]
            self._invariant(state.current_weight_kg <= profile.max_weight_kg, "vehicle_capacity weight")
            self._invariant(state.current_volume_liters <= profile.max_volume_liters, "vehicle_capacity volume")
            self._drain_finished_phases()
        else:
            state.orders_skipped += 1
            if response.binding_constraint in {"mandatory_break", "heat_rule"}:
                self._start_break()
        self._refresh_execution()

    def _shock(self, source: Event):
        shock = Shock.model_validate(source)
        self._emit("shock", **shock.model_dump(mode="json", exclude={"event", "sim_time"}, exclude_none=True), source_event=source)
        before = self.world.rain_factor
        shock_id, expiry = apply_shock(self.world, shock)
        for job in self.state.in_flight_orders:
            if shock.shock_type == "delay" and job.offer.order_id == shock.order_id:
                job.add_delay(shock.slip_min)
            if shock.shock_type == "closure" and (shock.zone is None or shock.zone in {job.offer.zone_pickup, job.offer.zone_dropoff}):
                job.add_delay(self.config.simulation.closure_delay_min)
        self._rescale_rain(before)
        if expiry:
            self._push(expiry, 1, "expiry", shock_id)
        self._drain_finished_phases()
        self._refresh_execution()

    def _rescale_rain(self, before: float):
        factor = self.world.rain_factor / before
        for job in self.state.in_flight_orders:
            for phase in job.phases:
                if phase.kind != "waiting":
                    phase.remaining_us = round(phase.remaining_us * factor)

    def run(self, stream: list[Event]) -> ShiftResult:
        if self._used:
            raise ValueError("Create a new simulator and agent for each independent run")
        self._used = True
        source = deepcopy(stream)
        self._validate_stream(source)
        digest = sha256(encode_events(source)).hexdigest()
        priorities = {"shift_start": -1, "shock": 2, "order_offered": 3, "shift_end": 9}
        for event in source:
            self._push(event_time(event), priorities[event["event"]], event["event"], event)
        while self._queue:
            when, _, _, kind, payload = heapq.heappop(self._queue)
            if kind == "phase" and payload != self._work_version:
                continue
            self._advance(when)
            if kind == "shift_start":
                self._emit("shift_start", **{k: v for k, v in payload.items() if k not in {"event", "sim_time"}},
                           source_event=payload, simulation_config=self.config.model_dump(mode="json"),
                           strategy_snapshot=self.agent.snapshot.model_dump(mode="json"),
                           agent_name=self.agent.name, simulator_version="mvp2-v1", stream_sha256=digest)
                self._position(action="shift_started")
            elif kind == "order_offered":
                self._offer(payload)
            elif kind == "shock":
                self._shock(payload)
            elif kind == "phase":
                self._drain_finished_phases()
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
                break
        return ShiftResult(self.agent.name, self.config.seed, digest, deepcopy(self.state),
                           collect_metrics(self.log.events), self.log)

    def _validate_stream(self, stream: list[Event]):
        if not stream or stream[0]["event"] != "shift_start" or stream[-1]["event"] != "shift_end":
            raise ValueError("Stream must start/end with shift boundaries")
        if sum(event["event"] == "shift_start" for event in stream) != 1 or sum(event["event"] == "shift_end" for event in stream) != 1:
            raise ValueError("Exactly one shift_start and shift_end required")
        if event_time(stream[0]) != self.state.shift_start or event_time(stream[-1]) != self.state.shift_end:
            raise ValueError("Stream boundaries disagree with ShiftConfig")
        expected = {"seed": self.config.seed, "shift_hours": self.config.shift_hours,
                    "vehicle": self.config.vehicle, "start_location_zone": self.config.start_location_zone,
                    "shift_end_time": self.state.shift_end.isoformat()}
        if any(stream[0].get(key) != value for key, value in expected.items()):
            raise ValueError("shift_start fields disagree with ShiftConfig")
        ids = set()
        previous = self.state.shift_start
        for event in stream:
            when = event_time(event)
            if when < previous or when > self.state.shift_end:
                raise ValueError("Exogenous stream must be chronological within the shift")
            previous = when
            if event["event"] not in {"shift_start", "shift_end", "shock", "order_offered"}:
                raise ValueError("Only exogenous events belong in generator stream")
            if event["event"] == "order_offered":
                order = DecideRequest.model_validate(event)
                if order.vehicle != self.state.vehicle or order.order_id in ids or when >= self.state.shift_end:
                    raise ValueError("Offers must have unique IDs, matching vehicle, and precede shift end")
                ids.add(order.order_id)
