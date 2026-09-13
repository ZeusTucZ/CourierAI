"""MVP 3 extension of the MVP 2 event loop and safety/accounting primitives."""
from copy import deepcopy
from datetime import timedelta
from time import perf_counter_ns

from app.agents.base import decision_request
from app.agents.smart import SmartAgent
from app.decision.constraints import evaluate_constraints
from app.decision.timing import WorkPlan
from app.models.requests import DecideRequest
from app.models.responses import DecideResponse
from app.models.state import resolve_state
from app.services.strategy_store import StrategyStore
from app.simulation.simulator import Simulator
from app.simulation.state import ActiveOrder, MINUTE_US, Phase, to_us
from app.strategy.cancellation import CancellationPolicy
from app.strategy.reposition import choose_reposition, zone_distance
from app.strategy.routing import insert_order, route_plan, steps_for
from app.strategy.routing import inspect_insert_order
from app.strategy.sla import compute_delivery_deadline
from app.strategy.updater import StrategyUpdater


class StrategicSimulator(Simulator):
    def __init__(self, config, agent, model, policy, *, unavailable_updates=()):
        super().__init__(config, agent)
        self.model, self.policy = model, policy
        self.initial_snapshot = agent.snapshot
        self.unavailable_updates = tuple(unavailable_updates)
        self.updater = StrategyUpdater(model, policy, range(1, config.simulation.zone_count + 1))
        self.store = agent.service.strategies if isinstance(agent, SmartAgent) else StrategyStore(agent.snapshot)
        self.route = []
        self.trace = []
        self.disruptions = {}
        self.move = None
        self.last_move = None
        self.move_version = 0
        self.deadhead_distance_km = 0

    def _trace(self, kind, **fields):
        self.trace.append({"type": kind, "sim_time": self.state.current_sim_time.isoformat(), **fields})

    def _emit(self, name, **fields):
        if name == "shift_start":
            fields.update(simulator_version="mvp3-v1", strategy_policy=self.policy.model_dump(mode="json"),
                          historical_model=self.model.model_dump(mode="json"),
                          unavailable_updates=list(self.unavailable_updates))
        super()._emit(name, **fields)

    def _schedule_extensions(self):
        at = self.state.shift_start
        number = 0
        while at < self.state.shift_end:
            self._push(at, 2.5, "strategy_tick", number)
            at += timedelta(minutes=self.policy.update_interval_min)
            number += 1

    def _internal_event(self, kind, payload):
        if kind == "strategy_tick":
            if isinstance(self.agent, SmartAgent):
                snapshot = self.updater.update(self.store, self.state.current_sim_time, self.state.vehicle,
                    (self.state.shift_end - self.state.current_sim_time).total_seconds() / 60,
                    available=payload not in self.unavailable_updates)
                self.agent.snapshot = snapshot
                self._emit("strategy_update", reservation_wage_mxn_hr=snapshot.reservation_wage_mxn_hr,
                    target_zone=snapshot.target_zone, degraded=snapshot.is_stale,
                    snapshot=snapshot.model_dump(mode="json"), reasoning="Historical zone/hour strategy refreshed between pings.")
                self._trace("strategy_update", snapshot=snapshot.model_dump(mode="json"))
            self._maybe_reposition()
        elif kind == "reposition_end":
            if self.move and payload == self.move_version:
                self.state.current_zone = self.move[0].zone
                self._trace("reposition_completed", zone=self.state.current_zone)
                self.move = None
                self.state.status = "idle"
                self.last_move = self.state.current_sim_time
                self._position(action="reposition_completed")
                self._refresh_execution()
        else:
            super()._internal_event(kind, payload)

    def _advance(self, when):
        if not self.move:
            if self.route:
                head = self.route[0].order_id
                self.state.in_flight_orders.sort(key=lambda job: job.offer.order_id != head)
            before = self.state.distance_traveled_km
            pickup = self.route and self.route[0].phase.kind == "to_pickup"
            super()._advance(when)
            if pickup:
                self.deadhead_distance_km += self.state.distance_traveled_km - before
            return
        action, phase = self.move
        elapsed = round((when - self.state.current_sim_time).total_seconds() * 1_000_000)
        self._invariant(0 <= elapsed <= phase.remaining_us and when <= self.state.shift_end, "reposition chronology")
        distance = phase.distance_km if elapsed == phase.remaining_us else phase.distance_km * elapsed / phase.remaining_us
        cost = distance * self.agent.snapshot.vehicle_profiles[self.state.vehicle].operating_cost_mxn_per_km
        self.state.continuous_riding_us += elapsed
        self._invariant(self.state.continuous_riding_min <= self.agent.snapshot.policy.mandatory_riding_limit_min, "reposition mandatory_break")
        if self.state.current_sim_time.hour < 16 and when.hour >= 12:
            self._invariant(self.state.continuous_riding_min <= 90, "reposition heat_rule")
        self.state.distance_traveled_km += distance
        self.state.operating_costs += cost
        self.state.reposition_distance_km += distance
        self.state.reposition_cost_mxn += cost
        self.deadhead_distance_km += distance
        phase.distance_km -= distance
        phase.remaining_us -= elapsed
        self.state.current_sim_time = when

    def _maybe_reposition(self):
        if self.move or not isinstance(self.agent, SmartAgent):
            return
        action = self._reposition_action()
        if action is None:
            return
        now = self.state.current_sim_time
        end = now + timedelta(minutes=action.travel_min)
        probe = DecideRequest(order_id="__REPOSITION__", sim_time=now, zone_pickup=self.state.current_zone,
            zone_dropoff=action.zone, distance_pickup_km=action.distance_km, distance_delivery_km=0,
            base_pay_mxn=0, surge_multiplier=1, weight_kg=0, volume_liters=0, vehicle=self.state.vehicle)
        resolved = resolve_state(now, self.state.overrides(), self.agent.snapshot.policy.default_shift_hours)
        plan = WorkPlan(action.travel_min, action.travel_min, action.travel_min, end, ((now, end),), ((action.zone, end),), False)
        if evaluate_constraints(probe, resolved, self.agent.snapshot, plan):
            self._start_break()
            return
        self.move = (action, Phase("to_pickup", to_us(action.travel_min), action.distance_km))
        self.move_version += 1
        self.state.reposition_count += 1
        self.state.status = "to_pickup"
        self._push(end, 0, "reposition_end", self.move_version)
        self._trace("reposition_started", target_zone=action.zone, distance_km=action.distance_km,
                    expected_gain_mxn=action.gain_mxn, expected_cost_mxn=action.operating_cost_mxn)
        self._position(action="reposition_started", target_zone=action.zone)

    def _reposition_action(self):
        return choose_reposition(self.state, self.agent.snapshot, self.policy, self.last_move, self.world.rain_factor)

    def _sync_route(self):
        """Insert newly created delay phases while preserving existing stop order."""
        jobs = {job.offer.order_id: job for job in self.state.in_flight_orders}
        self.route = [step for step in self.route if step.order_id in jobs and any(step.phase is p for p in jobs[step.order_id].phases)]
        for job in jobs.values():
            for index, phase in enumerate(job.phases):
                if any(step.phase is phase for step in self.route):
                    continue
                from app.strategy.routing import RouteStep
                following = job.phases[index + 1:]
                position = next((i for i, step in enumerate(self.route) if any(step.phase is p for p in following)), len(self.route))
                self.route.insert(position, RouteStep(job.offer.order_id, phase, job.offer.zone_pickup))

    def _remaining_violation(self):
        if not self.route:
            return None
        first = self.state.in_flight_orders[0]
        remaining = first.remaining()
        overrides = self.state.overrides().model_copy(update={"in_flight_orders": tuple(job.remaining() for job in self.state.in_flight_orders[1:])})
        request = DecideRequest.model_validate({**first.offer.model_dump(), **remaining.model_dump(exclude={"order_id"}),
                    "sim_time": self.state.current_sim_time, "courier_state_overrides": overrides})
        resolved = resolve_state(request.sim_time, overrides, self.agent.snapshot.policy.default_shift_hours)
        plan, _ = route_plan(self.route, request.sim_time)
        return evaluate_constraints(request, resolved, self.agent.snapshot, plan)

    def _refresh_execution(self):
        if self.move:
            return
        self._sync_route()
        _, completion = route_plan(self.route, self.state.current_sim_time)
        for job in self.state.in_flight_orders:
            job.estimated_completion_time = completion[job.offer.order_id]
        if isinstance(self.agent, SmartAgent) and self.policy.use_smart_v2_scoring and self.route:
            margins = {job.offer.order_id:
                (job.promised_completion_time - completion[job.offer.order_id]).total_seconds() / 60
                for job in self.state.in_flight_orders}
            self._trace("route_metrics_updated",
                commitment_horizon_min=sum(step.phase.remaining_us for step in self.route) / MINUTE_US,
                route_eta={key: value.isoformat() for key, value in completion.items()},
                sla_margins_min=margins,
                minimum_sla_margin_min=min(margins.values()))
        violation = self._remaining_violation()
        previous = self.state.execution_hold
        self.state.execution_hold = violation.constraint if violation else None
        if violation and previous != violation.constraint:
            self.state.post_accept_infeasible += 1
            self._position(action="post_accept_infeasible", binding_constraint=violation.constraint, reason=violation.reason)
        elif previous and not violation:
            self._position(action="execution_resumed")
        self._work_version += 1
        if self.state.execution_hold:
            self.state.status = "waiting"
        elif self.route:
            step = self.route[0]
            self.state.status = step.phase.kind
            self._push(self.state.current_sim_time + timedelta(microseconds=step.phase.remaining_us), 0, "phase", self._work_version)
        else:
            self.state.status = "on_break" if self.state.break_until else "idle"
        self._position(action="state_updated")
        if not self.route:
            self._maybe_reposition()

    def _drain_finished_phases(self):
        while self.route and not self.state.execution_hold and self.route[0].phase.remaining_us == 0:
            step = self.route.pop(0)
            job = next(job for job in self.state.in_flight_orders if job.offer.order_id == step.order_id)
            self._invariant(job.phases[0] is step.phase, "pickup before delivery / phase order")
            phase = job.phases.pop(0)
            if phase.distance_km:
                if phase.kind == "to_pickup":
                    self.deadhead_distance_km += phase.distance_km
                self.state.distance_traveled_km += phase.distance_km
                self.state.operating_costs += phase.distance_km * self.agent.snapshot.vehicle_profiles[self.state.vehicle].operating_cost_mxn_per_km
            if phase.kind != "waiting":
                self.state.current_zone = step.zone
                if phase.kind == "to_dropoff":
                    self._invariant(not (step.zone in self.agent.snapshot.flagged_zones and self.state.current_sim_time.hour >= 22), "flagged_zone_night")
                self._position(action="pickup_arrival" if phase.kind == "to_pickup" else "dropoff_arrival", order_id=step.order_id)
            if not job.phases:
                self.state.in_flight_orders.remove(job)
                self.state.gross_earnings += job.offer.base_pay_mxn * job.offer.surge_multiplier + job.offer.est_tip_mxn
                self.state.orders_completed += 1
                late = self.state.current_sim_time > job.promised_completion_time
                disrupted = late and job.offer.order_id in self.disruptions
                self.state.late_deliveries += int(late)
                self.state.disruption_caused_lateness += int(disrupted)
                self._earnings(completed_order_id=job.offer.order_id, late=late,
                    disruption_caused_lateness=disrupted, promised_completion_time=job.promised_completion_time.isoformat())

    def _prepare_offer(self, source):
        # Same source world, independently observable pickup travel from actual position.
        adjusted = {**source, "distance_pickup_km": source["distance_pickup_km"] + zone_distance(
            self.state.current_zone, source["zone_pickup"], self.policy.synthetic_zone_spacing_km)}
        return self.world.prepare_offer(adjusted, self.agent.snapshot)

    def _candidate(self, job, request):
        return insert_order(self.route, job, self.state.in_flight_orders, request, self.agent.snapshot,
            self.policy, improved=isinstance(self.agent, SmartAgent) and self.policy.use_improved_batching) if not self.move else None

    def _candidate_diagnostics(self, job, request):
        if self.move:
            from app.strategy.routing import InsertionDiagnostics
            return InsertionDiagnostics(None, "active_commitment", 0, 0, 0, None)
        return inspect_insert_order(self.route, job, self.state.in_flight_orders, request,
            self.agent.snapshot, self.policy,
            improved=isinstance(self.agent, SmartAgent) and self.policy.use_improved_batching)

    @staticmethod
    def _route_distance(sequence):
        return sum(step.phase.distance_km for step in sequence)

    def _smart_v2_details(self, order, candidate, deadline):
        sequence, candidate_plan = candidate
        now = self.state.current_sim_time
        current_plan, _ = route_plan(self.route, now)
        _, completion = route_plan(sequence, now, order.order_id)
        deadlines = {job.offer.order_id: job.promised_completion_time
                     for job in self.state.in_flight_orders}
        deadlines[order.order_id] = deadline
        margins = {key: (deadlines[key] - arrival).total_seconds() / 60
                   for key, arrival in completion.items()}
        current_distance = self._route_distance(self.route)
        candidate_distance = self._route_distance(sequence)
        minimum_margin = min(margins.values())
        details = self.agent.score_route_candidate(order,
            current_plan=current_plan, candidate_plan=candidate_plan,
            current_distance_km=current_distance, candidate_distance_km=candidate_distance,
            minimum_sla_margin_min=minimum_margin, policy=self.policy)
        details["sla_margins_min"] = margins
        return details

    @staticmethod
    def _smart_v2_reason(details, accepted):
        if details["mode"] == "idle":
            horizon = details["commitment_horizon_min"]
            if accepted:
                qualifier = "strong net value" if details["final_score_mxn"] >= 20 else "positive net value"
                return f"Accepted: {horizon:.1f} min idle commitment has {qualifier} after commitment risk."
            return (f"Skipped: {horizon:.1f} min idle commitment loses value after a "
                    f"MXN {details['commitment_penalty_mxn']:.1f} commitment penalty.")
        if accepted:
            return (f"Accepted: batch adds {details['incremental_time_min']:.1f} min and "
                    f"{details['incremental_distance_km']:.1f} km while preserving SLA margin.")
        if details["decision_cause"] == "sla_risk":
            return (f"Skipped: batch leaves only {details['minimum_sla_margin_min']:.1f} min SLA margin "
                    "and insufficient risk-adjusted value.")
        return (f"Skipped: batch adds {details['incremental_time_min']:.1f} min for insufficient "
                "incremental net value.")

    def _commit_candidate(self, sequence, job):
        self.route = sequence
        self.state.in_flight_orders.append(job)

    def _offer(self, source):
        order = self._prepare_offer(source)
        request = decision_request(order, self.state)
        self._emit("order_offered", **order.model_dump(mode="json", exclude={"event", "sim_time", "courier_state_overrides"}, exclude_none=True), source_event=source)
        deadline = compute_delivery_deadline(order, self.state, self.policy)
        job = ActiveOrder.accepted(order, self.agent.snapshot, deadline)
        insertion = self._candidate_diagnostics(job, request)
        candidate = insertion.candidate
        started = perf_counter_ns()
        if candidate:
            sequence, plan = candidate
            response = self.agent.service.decide(request, plan=plan) if isinstance(self.agent, SmartAgent) else self.agent.decide_request(request)
        else:
            response = self.agent.decide_request(request)
            cause = insertion.decision_cause or "hard_constraint"
            if response.decision == "ACCEPT" or cause in {"sla_infeasible", "active_commitment"}:
                reason = ({
                    "sla_infeasible": "Skipped: no insertion preserves every active and candidate SLA deadline.",
                    "capacity": "Skipped: active-order capacity leaves no feasible insertion.",
                    "active_commitment": "Skipped: active repositioning prevents a feasible route insertion.",
                }.get(cause, "Skipped: no insertion satisfies the active hard constraints."))
                response = response.model_copy(update={"decision": "SKIP", "binding_constraint": None,
                    "reason": reason})
        details = None
        if isinstance(self.agent, SmartAgent) and self.policy.use_smart_v2_scoring:
            if candidate:
                details = self._smart_v2_details(request, candidate, deadline)
                accepted = details["final_score_mxn"] >= 0
                details["decision"] = "ACCEPT" if accepted else "SKIP"
                response = response.model_copy(update={
                    "decision": details["decision"],
                    "binding_constraint": None,
                    "reason": self._smart_v2_reason(details, accepted),
                })
            else:
                details = {
                    "mode": "batching" if self.state.in_flight_orders else "idle",
                    "decision_cause": insertion.decision_cause,
                    "minimum_sla_margin_min": insertion.best_rejected_sla_margin_min,
                    "candidates_considered": insertion.candidates_considered,
                    "deadline_rejections": insertion.deadline_rejections,
                    "constraint_rejections": insertion.constraint_rejections,
                    "decision": "SKIP",
                }
            self.agent.service.log.amend_latest(order.order_id, response, details)
        self.state.orders_offered += 1
        response = response.model_copy(update={"latency_ms": (perf_counter_ns() - started) / 1e6})
        self._emit("decision", **response.model_dump(mode="json"), decision_request=request.model_dump(mode="json"),
                   courier_state=self.state.summary(), strategy_snapshot=self.agent.snapshot.model_dump(mode="json"),
                   delivery_deadline=deadline.isoformat(), insertion_feasible=candidate is not None,
                   planned_route=[[step.order_id, step.phase.kind] for step in candidate[0]] if candidate else [],
                   **({"smart_v2": details} if details is not None else {}))
        if response.decision == "ACCEPT":
            self._commit_candidate(candidate[0], job)
            self.state.orders_accepted += 1
            self._drain_finished_phases()
        else:
            self.state.orders_skipped += 1
            self.state.skip_penalties += self.policy.skip_penalty_mxn
            if response.binding_constraint in {"mandatory_break", "heat_rule"} and not self.move:
                self._start_break()
        self._refresh_execution()

    def _shock(self, source):
        previous_eta = {job.offer.order_id: job.estimated_completion_time for job in self.state.in_flight_orders}
        # Eligibility is recorded only for work exposed to this actual visible shock.
        affected = [job for job in self.state.in_flight_orders if source["shock_type"] == "rain" or
            source["shock_type"] == "delay" and source.get("order_id") == job.offer.order_id or
            source["shock_type"] == "closure" and (source.get("zone") is None or source["zone"] in {job.offer.zone_pickup, job.offer.zone_dropoff})]
        for job in affected:
            self.disruptions[job.offer.order_id] = deepcopy(source)
        super()._shock(source)
        # Propagated queue delay retains the actual visible triggering shock.
        if source["shock_type"] in {"closure", "rain", "delay"}:
            for job in self.state.in_flight_orders:
                if job.estimated_completion_time > previous_eta[job.offer.order_id]:
                    self.disruptions[job.offer.order_id] = deepcopy(source)
        policy = CancellationPolicy(self.policy)
        for job in list(self.state.in_flight_orders):
            trigger = self.disruptions.get(job.offer.order_id)
            if trigger is None:
                continue
            minutes = sum(p.remaining_us for p in job.phases) / MINUTE_US
            late = max(0, (job.estimated_completion_time - job.promised_completion_time).total_seconds() / 60)
            prediction = self.agent.snapshot.zone_predictions.get(self.state.current_zone)
            cost = sum(p.distance_km for p in job.phases) * self.agent.snapshot.vehicle_profiles[self.state.vehicle].operating_cost_mxn_per_km
            choice = policy.evaluate(triggering_shock=trigger, remaining_net=job.offer.base_pay_mxn * job.offer.surge_multiplier + job.offer.est_tip_mxn - cost,
                remaining_min=minutes, lateness_min=late, expected_rate=(prediction.expected_net_mxn_per_hour or 0) if prediction else 0,
                infeasible=self.state.execution_hold is not None)
            self._trace("cancellation_evaluated", order_id=job.offer.order_id, triggering_shock=trigger,
                estimated_continue_value=choice.continue_value, estimated_cancel_value=choice.cancel_value, cancel=choice.cancel,
                cancellation_reason=choice.reason, revised_eta=job.estimated_completion_time.isoformat())
            if choice.cancel:
                self.state.in_flight_orders.remove(job)
                self.state.orders_cancelled += 1
                self.state.cancellation_penalties += self.policy.cancellation_penalty_mxn
                self._position(action="order_cancelled", order_id=job.offer.order_id,
                    cancellation_reason=choice.reason, triggering_shock=trigger,
                    estimated_continue_value=choice.continue_value, estimated_cancel_value=choice.cancel_value)
        self._refresh_execution()

    def _rescale_rain(self, before):
        super()._rescale_rain(before)
        if self.move and self.world.rain_factor != before:
            # Stop/reprice an in-progress reposition at a shock boundary; keep
            # all already incurred costs. No unsafe travel after a changed ETA.
            self.move = None
            self.move_version += 1
            self.last_move = self.state.current_sim_time
            self.state.status = "idle"
            self._trace("reposition_interrupted", reason="weather_changed", zone=self.state.current_zone)

    def _earnings(self, **fields):
        state = self.state
        self._emit("earnings_update", earnings_mxn=state.net_earnings, gross_earnings_mxn=state.gross_earnings,
            operating_costs_mxn=state.operating_costs, orders_completed=state.orders_completed,
            distance_traveled_km=state.distance_traveled_km, idle_time_min=state.idle_time_min,
            late_deliveries=state.late_deliveries, safety_violations=state.safety_violations,
            orders_cancelled=state.orders_cancelled, skip_penalties_mxn=state.skip_penalties,
            cancellation_penalties_mxn=state.cancellation_penalties, reposition_count=state.reposition_count,
            reposition_distance_km=state.reposition_distance_km, reposition_cost_mxn=state.reposition_cost_mxn,
            deadhead_distance_km=self.deadhead_distance_km,
            # This is observed net after move costs, NOT a causal gain estimate.
            net_gain_after_reposition=state.net_earnings if state.reposition_count else 0,
            **({"disruption_caused_lateness": state.disruption_caused_lateness} if "disruption_caused_lateness" not in fields else {}), **fields)
