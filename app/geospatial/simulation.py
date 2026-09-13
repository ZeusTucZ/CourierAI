"""Geographic execution adapter. Existing agents, sequence selector and safety rules are reused."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import replace

from app.agents.smart import SmartAgent
from app.decision.constraints import evaluate_constraints
from app.decision.timing import build_work_plan
from app.models.state import resolve_state
from app.simulation.strategic import StrategicSimulator
from app.simulation.state import to_us, MINUTE_US
from app.strategy.routing import insert_order, route_plan
from app.strategy.routing import InsertionDiagnostics
from app.geospatial.routing import NoRoute
from app.geospatial.geometry import line, point
from app.geospatial.cache import digest


class GeospatialSimulator(StrategicSimulator):
    routing_source = "osm"

    def __init__(self, config, agent, model, policy, planner):
        super().__init__(config, agent, model, policy)
        self.planner = planner
        self.state.current_node = planner.store.node(self.state.current_zone)
        self.routing_trace = []
        self._geo_version = planner.closures.version(self.state.current_sim_time)
        self._pending_move = None
        self._no_route = False
        self._sequence_signature = ()
        self._completed_ids = set()

    def _earnings(self, **fields):
        if fields.get("completed_order_id"):
            self._completed_ids.add(fields["completed_order_id"])
        super()._earnings(**fields)

    def _emit(self, name, **fields):
        if name == "shift_start":
            fields.update(routing_source="osm", graph_version=self.planner.store.metadata["graph_version"],
                          zone_mapping_version=self.planner.store.zones.version)
        if name in {"position_update", "shift_end"}:
            fields["current_node"] = self.state.current_node
        super()._emit(name, **fields)

    def _record(self, kind, **fields):
        self.routing_trace.append({"type": kind, "agent": self.agent.name,
            "sim_time": self.state.current_sim_time.isoformat(),
            "graph_version":self.planner.store.metadata["graph_version"],
            "zone_mapping_version":self.planner.store.zones.version,
            "closure_version":self.planner.closures.version(self.state.current_sim_time), **fields})

    def _leg(self, origin, zone):
        return self.planner.route_nodes(origin,self.planner.store.node(zone),self.state.vehicle,
            now=self.state.current_sim_time,rain_factor=self.world.rain_factor)

    def _prepare_offer(self, source):
        pickup = self._leg(self.state.current_node, source["zone_pickup"])
        delivery = self._leg(self.planner.store.node(source["zone_pickup"]), source["zone_dropoff"])
        adjusted = {**source, "distance_pickup_km":pickup["distance_km"],"distance_delivery_km":delivery["distance_km"],
            "estimated_pickup_min":pickup["base_eta_min"],"estimated_delivery_min":delivery["base_eta_min"]}
        order = self.world.prepare_offer(adjusted,self.agent.snapshot)
        # OSM overlay replaces synthetic closure preparation penalties. Rain is applied by WorldState once.
        penalties = sum(self.config.simulation.closure_delay_min for shock in self.world.active.values()
            if shock.shock_type == "closure" and (shock.zone is None or shock.zone in {order.zone_pickup,order.zone_dropoff}))
        order = order.model_copy(update={"restaurant_prep_min":max(0,order.restaurant_prep_min-penalties)})
        self._record("offer_routes",order_id=order.order_id,pickup=pickup,delivery=delivery)
        return order

    def _offer(self, source):
        try:
            super()._offer(source)
        except NoRoute as exc:
            # Unreachable offers never reach an agent with a fabricated ETA.
            self.state.orders_offered += 1
            self.state.orders_skipped += 1
            self._emit("order_offered", **{k:v for k,v in source.items() if k not in {"event","sim_time"}},
                       route_feasible=False, source_event=source)
            self._emit("decision",order_id=source["order_id"],decision="SKIP",binding_constraint=None,
                reason="Skipped: no open directed road route connects the required stops.",latency_ms=0,tier="tier1",degraded=False)
            self._record("unreachable_offer",order_id=source["order_id"],reason=str(exc))

    def _segments(self, route):
        segments = [{"edge":tuple(e), "distance":float(self.planner.graph.edges[tuple(e)]["length"])/1000,
                     "us":to_us(self.planner.edge_minutes(tuple(e),self.state.vehicle)*self.world.rain_factor)}
                    for e in route["edge_path"]]
        return segments

    def _price(self, sequence, *, record=False):
        node = self.state.current_node
        changed = []
        for step in sequence:
            phase = step.phase
            if phase.kind == "waiting":
                continue
            old = getattr(phase,"geo",None)
            prefix = []
            # A courier already on an edge may exit it; closures prevent new entry.
            if old and old["segments"] and old.get("entered"):
                prefix = [deepcopy(old["segments"][0])]
                node = prefix[0]["edge"][1]
            result = self._leg(node,step.zone)
            segments = prefix + self._segments(result)
            distance = sum(s["distance"] for s in segments)
            duration = sum(s["us"] for s in segments)
            if prefix:
                first_node=prefix[0]["edge"][0]
                longitude,latitude=point(self.planner.graph,first_node)
                result["origin"]={"node":first_node,"lon":longitude,"lat":latitude}
                result["edge_path"]=[list(s["edge"]) for s in segments]
                result["node_path"]=[segments[0]["edge"][0]]+[s["edge"][1] for s in segments]
                result["geometry"]=line(self.planner.graph,[s["edge"] for s in segments],self.state.current_node)
                result["distance_km"],result["eta_min"]=distance,duration/MINUTE_US
                result["base_eta_min"]=result["eta_min"]/self.world.rain_factor
                result["occupied_edge_exit"]=list(prefix[0]["edge"])
                result["route_hash"]=digest([result["graph_version"],result["edge_path"],distance,duration])
            changed.append((phase, distance, duration, {"segments":segments,"entered":bool(prefix),
                "destination":self.planner.store.node(step.zone),"route":result}))
            if record:
                self._record("active_route",order_id=step.order_id,phase=phase.kind,route=result,
                    occupied_edge_exit=list(prefix[0]["edge"]) if prefix else None,
                    old_distance_km=phase.distance_km,new_distance_km=distance,
                    old_eta_min=phase.remaining_us/MINUTE_US,new_eta_min=duration/MINUTE_US,
                    detour_distance_km=distance-phase.distance_km,detour_minutes=(duration-phase.remaining_us)/MINUTE_US)
            node = self.planner.store.node(step.zone)
        for phase,distance,duration,geo in changed:
            phase.distance_km,phase.remaining_us,phase.geo = distance,duration,geo

    def _candidate(self, job, request):
        if self.move:
            return None
        # Use existing bounded sequencing unchanged, then quote its chosen stop order on OSM.
        route, new_job, jobs = deepcopy((self.route,job,self.state.in_flight_orders))
        candidate = insert_order(route,new_job,jobs,request,self.agent.snapshot,self.policy,
            improved=isinstance(self.agent,SmartAgent) and self.policy.use_improved_batching)
        if candidate is None:
            return None
        sequence,_ = candidate
        try:
            self._price(sequence)
        except NoRoute:
            return None
        plan,completion = route_plan(sequence,request.sim_time,job.offer.order_id)
        if any(completion[j.offer.order_id]>j.promised_completion_time for j in (*jobs,new_job)):
            return None
        state = resolve_state(request.sim_time,request.courier_state_overrides,self.agent.snapshot.policy.default_shift_hours)
        if evaluate_constraints(request,state,self.agent.snapshot,plan):
            return None
        return sequence,plan

    def _candidate_diagnostics(self, job, request):
        candidate = self._candidate(job, request)
        state = resolve_state(request.sim_time, request.courier_state_overrides,
                              self.agent.snapshot.policy.default_shift_hours)
        isolated_violation = evaluate_constraints(request, state, self.agent.snapshot,
                                                  build_work_plan(request, state, self.agent.snapshot))
        cause = (None if candidate else "active_commitment" if self.move else
                 "hard_constraint" if isolated_violation else "sla_infeasible")
        return InsertionDiagnostics(candidate, cause, 1, int(candidate is None and not self.move),
                                    0, None)

    def _commit_candidate(self, sequence, job):
        super()._commit_candidate(sequence,job)
        for existing in self.state.in_flight_orders:
            existing.phases = [s.phase for s in sequence if s.order_id==existing.offer.order_id]
        self._price(self.route,record=True)

    def _advance(self, when):
        if self.move and self.state.execution_hold:
            self.state.current_sim_time=when
            return
        phase = self.move[1] if self.move else self.route[0].phase if self.route else None
        geo = getattr(phase,"geo",None)
        elapsed = round((when-self.state.current_sim_time).total_seconds()*1e6)
        before_distance = self.state.distance_traveled_km
        old_phase_distance = phase.distance_km if phase else 0
        held = bool(self.state.execution_hold)
        super()._advance(when)
        if geo and not held:
            remaining, traveled = elapsed, 0.
            while geo["segments"]:
                segment = geo["segments"][0]
                used = min(remaining,segment["us"])
                distance = segment["distance"] * used/segment["us"] if segment["us"] else segment["distance"]
                segment["distance"]-=distance
                segment["us"]-=used
                traveled+=distance
                remaining-=used
                if not segment["us"]:
                    self.state.current_node=segment["edge"][1]
                    geo["segments"].pop(0)
                    geo["entered"]=False
                else:
                    geo["entered"] = geo.get("entered",False) or used>0
                    break
                if remaining==0:
                    break
            if not geo["segments"]:
                self.state.current_node=geo["destination"]
            correction = traveled-(self.state.distance_traveled_km-before_distance)
            self.state.distance_traveled_km+=correction
            self.state.operating_costs+=correction*self.agent.snapshot.vehicle_profiles[self.state.vehicle].operating_cost_mxn_per_km
            if phase.kind=="to_pickup":
                self.deadhead_distance_km+=correction
            if self.move:
                self.state.reposition_distance_km+=correction
                self.state.reposition_cost_mxn+=correction*self.agent.snapshot.vehicle_profiles[self.state.vehicle].operating_cost_mxn_per_km
            phase.distance_km=max(0,old_phase_distance-traveled)

    def _drain_finished_phases(self):
        # Include zero-length same-node legs before the parent consumes them.
        for step in self.route:
            if step.phase.remaining_us:
                break
            geo = getattr(step.phase,"geo",None)
            if geo:
                self.state.current_node=geo["destination"]
        super()._drain_finished_phases()

    def _closure_delay(self, job):
        pass  # Geographic detour replaces the synthetic fixed delay.

    def _shock(self, source):
        if source["shock_type"]=="closure":
            road = source.get("road")
            edges = ()
            # Explicit edge encoding stays within the official optional road string.
            if road and road.startswith("edge:"):
                edges = [tuple(map(int,road[5:].split(":")))]
                road = None
            closure = self.planner.closures.add(f"sim-{self.world.next_id}",self.state.current_sim_time,
                source["duration_min"],road=road,edges=edges,zone=source.get("zone") if not road and not edges else None)
            self._record("closure",closure_id=closure.closure_id,edges=closure.blocked_edges)
        super()._shock(source)

    def _refresh_execution(self):
        self._sync_route()
        version = self.planner.closures.version(self.state.current_sim_time)
        changed = version != self._geo_version
        signature=tuple((s.order_id,s.phase.kind,id(s.phase)) for s in self.route)
        # A cancellation changes adjacent stops. Phase completion alone keeps already quoted successors.
        old_ids={item[0] for item in self._sequence_signature}
        removed=old_ids-{item[0] for item in signature}
        cancelled=bool(removed-self._completed_ids)
        if changed or self._no_route or cancelled:
            try:
                self._price(self.route,record=True)
                self._no_route=False
                self._geo_version=version
                if self.move:
                    from app.strategy.routing import RouteStep
                    self._price([RouteStep("__REPOSITION__",self.move[1],self.move[0].zone)],record=True)
                    if self._move_violation():
                        self.state.execution_hold="geographic_reposition_infeasible"
                        self.state.status="waiting"
                        self.move_version+=1
                        return
                    self.state.execution_hold=None
                    self.move_version+=1
                    self._push(self.state.current_sim_time+timedelta(microseconds=self.move[1].remaining_us),0,"reposition_end",self.move_version)
            except NoRoute:
                self._no_route=True
        if self._no_route:
            self.state.execution_hold="no_route"
            self.state.status="waiting"
            self._work_version+=1
            self._position(action="route_unreachable")
            return
        if self.state.execution_hold=="no_route":
            self.state.execution_hold=None
        self._sequence_signature=signature
        super()._refresh_execution()

    def _move_violation(self):
        from app.models.requests import DecideRequest
        from app.decision.timing import WorkPlan
        action,phase=self.move
        now=self.state.current_sim_time
        duration=phase.remaining_us/MINUTE_US
        end=now+timedelta(microseconds=phase.remaining_us)
        probe=DecideRequest(order_id="__REPOSITION__",sim_time=now,zone_pickup=self.state.current_zone,
            zone_dropoff=action.zone,distance_pickup_km=phase.distance_km,distance_delivery_km=0,
            base_pay_mxn=0,surge_multiplier=1,weight_kg=0,volume_liters=0,vehicle=self.state.vehicle)
        state=resolve_state(now,self.state.overrides(),self.agent.snapshot.policy.default_shift_hours)
        plan=WorkPlan(duration,duration,duration,end,((now,end),),((action.zone,end),),False)
        return evaluate_constraints(probe,state,self.agent.snapshot,plan)

    def _rescale_rain(self, before):
        phases = [p for j in self.state.in_flight_orders for p in j.phases]
        factor = self.world.rain_factor/before
        for phase in phases:
            geo=getattr(phase,"geo",None)
            if geo:
                for segment in geo["segments"]:
                    segment["us"]=round(segment["us"]*factor)
        super()._rescale_rain(before)
        for phase in phases:
            if hasattr(phase,"geo"):
                phase.remaining_us=sum(s["us"] for s in phase.geo["segments"])
                if factor != 1:
                    geo=phase.geo
                    self._record("rain_route_update",distance_km=phase.distance_km,
                        eta_min=phase.remaining_us/MINUTE_US,rain_factor=self.world.rain_factor,
                        geometry=line(self.planner.graph,[s["edge"] for s in geo["segments"]],self.state.current_node))

    def _reposition_action(self):
        # Existing strategic target selection stays intact. Requote its proposed move and reject unsafe/unprofitable geography.
        action = super()._reposition_action()
        if action is None:
            return None
        try:
            route=self._leg(self.state.current_node,action.zone)
        except NoRoute:
            return None
        profile=self.agent.snapshot.vehicle_profiles[self.state.vehicle]
        cost=route["distance_km"]*profile.operating_cost_mxn_per_km
        prediction=self.agent.snapshot.zone_predictions[action.zone]
        current=self.agent.snapshot.zone_predictions.get(self.state.current_zone)
        horizon=min(self.policy.reposition_horizon_min,(self.state.shift_end-self.state.current_sim_time).total_seconds()/60)
        gain=(prediction.expected_net_mxn_per_hour or 0)*max(0,horizon-route["eta_min"])/60-(current.expected_net_mxn_per_hour or 0 if current else 0)*horizon/60-cost
        if gain<=self.policy.minimum_reposition_gain:
            return None
        self._pending_move=route
        return replace(action,distance_km=route["distance_km"],travel_min=route["eta_min"],operating_cost_mxn=cost,gain_mxn=gain)

    def _maybe_reposition(self):
        was_moving=bool(self.move)
        super()._maybe_reposition()
        if self.move and not was_moving and self._pending_move:
            self.move[1].geo={"segments":self._segments(self._pending_move),"entered":False,
                "destination":self.planner.store.node(self.move[0].zone),"route":self._pending_move}
            self.move[1].remaining_us=sum(s["us"] for s in self.move[1].geo["segments"])
            self.move_version+=1
            self._push(self.state.current_sim_time+timedelta(microseconds=self.move[1].remaining_us),0,"reposition_end",self.move_version)
            self._record("reposition_route",route=self._pending_move)
            self._pending_move=None
