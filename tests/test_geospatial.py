"""Offline controlled road topology; real OSM smoke is a separate explicit command."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import socket

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.geospatial.graph import GraphStore
from app.geospatial.zones import ZoneRegistry
from app.geospatial.routing import RoutePlanner, NoRoute
from app.geospatial.simulation import GeospatialSimulator
from app.agents.nearby import FirstNearbyOrderBaseline, FirstNearbyBaselineConfig
from app.agents.smart import SmartAgent
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy
from app.main import create_app
from tests.mvp2_support import config, offer, shock, stream, selected
from validate_format import check_event_log

NOW=datetime(2026,3,21,18)


@pytest.fixture
def store():
    graph=nx.MultiDiGraph(crs="epsg:4326")
    for node in range(1,13):
        graph.add_node(node,x=-100.30+node*.001,y=25.65)
    for u in range(1,13):
        v=u%12+1
        for a,b in ((u,v),(v,u)):
            graph.add_edge(a,b,key=0,length=100.,speed_kph=25.,travel_time=14.4,name="Access Road")
    graph.add_edge(7,11,key=0,length=300.,speed_kph=25.,travel_time=43.2,name="Avenida Prueba")
    graph.add_edge(7,11,key=1,length=600.,speed_kph=25.,travel_time=86.4,name="Parallel Road")
    zones=ZoneRegistry()
    return GraphStore(graph,zones,{"graph_version":"fixture-v1","zone_mapping_version":zones.version},
        {z:{"node":z,"distance_m":0.} for z in zones.zones})


@pytest.fixture
def planner(store):
    return RoutePlanner(store)


@pytest.mark.parametrize("zone",range(1,13))
def test_zone_registry_and_snaps(store,zone):
    z=store.zones.zones[zone]
    assert z["name"] and 25.5<z["latitude"]<26 and -100.7<z["longitude"]<-100
    assert store.node(zone) in store.graph
    store.validate_connectivity()


@pytest.mark.parametrize("vehicle",["moto","car","bike"])
def test_shortest_paths_match_and_geometry(planner,vehicle):
    a=planner.route(7,11,vehicle)
    d=planner.route(7,11,vehicle,"dijkstra")
    assert a["eta_min"]==pytest.approx(d["eta_min"])
    assert a["distance_km"]==pytest.approx(d["distance_km"])
    assert a["distance_km"]>0 and a["eta_min"]>0
    assert a["edge_path"]==[[7,11,0]]
    assert a["geometry"]["coordinates"][0]==pytest.approx([-100.293,25.65])
    assert a["geometry"]["coordinates"][-1]==pytest.approx([-100.289,25.65])
    assert json.loads(json.dumps(a))==a


def test_closure_keyed_parallel_expiry_and_cache(planner):
    original=planner.route(7,11,now=NOW)
    before=deepcopy(dict(planner.graph.edges))
    planner.closures.add("c",NOW,5,edges=[(7,11,0)])
    changed=planner.route(7,11,now=NOW)
    assert [7,11,0] not in changed["edge_path"]
    assert changed["eta_min"]>original["eta_min"]
    assert changed["closure_version"]!=original["closure_version"]
    assert planner.route(7,11,now=NOW+timedelta(minutes=5))["node_path"]==original["node_path"]
    assert dict(planner.graph.edges)==before
    with pytest.raises(nx.NetworkXError):
        planner.graph.remove_edge(7,11,0)


def test_road_name_normalization_and_zone_policy(planner):
    c=planner.closures.add("c",NOW,1,road="Av. Prueba")
    assert c.blocked_edges==((7,11,0),)
    z=planner.closures.add("z",NOW,1,zone=11)
    assert len(z.blocked_edges)==1
    assert planner.closures.geojson(NOW)["features"][0]["geometry"]["type"]=="MultiLineString"
    with pytest.raises(ValueError):
        planner.closures.add("missing",NOW,1,road="not an actual road")


def test_overlapping_closures_and_future_start(planner):
    edge=(7,11,0)
    planner.closures.add("first",NOW,5,edges=[edge])
    planner.closures.add("second",NOW+timedelta(minutes=4),5,edges=[edge])
    assert edge in planner.closures.blocked(NOW+timedelta(minutes=6))
    assert not planner.closures.blocked(NOW+timedelta(minutes=9))
    assert not planner.closures.blocked(NOW-timedelta(seconds=1))


def test_rain_and_cache_return_isolation(planner):
    base=planner.route(7,11)
    rainy=planner.route(7,11,rain_factor=1.25)
    assert rainy["eta_min"]==base["eta_min"]*1.25
    assert rainy["geometry"]==base["geometry"]
    rainy["edge_path"].clear()
    assert planner.route(7,11)==base


def test_deterministic_order_and_no_network(store,monkeypatch):
    def forbidden(*a,**k):
        raise AssertionError("Unexpected network")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    assert RoutePlanner(store).route(7,11)==RoutePlanner(store).route(7,11)


def test_no_route_and_invalid_requests(planner):
    planner.closures.add("all",NOW,2,edges=list(planner.graph.out_edges(7,keys=True)))
    with pytest.raises(NoRoute):
        planner.route(7,11,now=NOW)
    with pytest.raises(ValueError):
        planner.route(99,11)
    with pytest.raises(ValueError):
        planner.route(7,11,rain_factor=float("nan"))


def simulator(planner,agent=None):
    cfg=config(hours=1)
    sim=GeospatialSimulator(cfg,agent or SmartAgent(),HistoricalDemandModel(),
        StrategyPolicy(use_reposition=False,use_cancellation=False),planner)
    return cfg,sim


@pytest.mark.parametrize("agent",["smart","nearby"])
def test_simulator_consumes_osm_and_completes(planner,tmp_path,agent):
    selected_agent=SmartAgent() if agent=="smart" else FirstNearbyOrderBaseline(FirstNearbyBaselineConfig.load())
    cfg,sim=simulator(planner,selected_agent)
    result=sim.run(stream(cfg,offer(cfg,zone_dropoff=11,distance_delivery_km=999)))
    request=selected(result,"decision")[0]["decision_request"]
    assert request["distance_delivery_km"]==pytest.approx(.3)
    assert request["estimated_delivery_min"]==pytest.approx(.72)
    assert result.state.orders_completed==1
    assert result.state.current_node==11 and result.state.safety_violations==0
    path=tmp_path/"events.jsonl"
    result.log.write(path)
    assert not check_event_log(path)[0]


def test_active_closure_changes_execution_and_commitments(planner):
    cfg,sim=simulator(planner)
    result=sim.run(stream(cfg,offer(cfg,zone_dropoff=12),shock(cfg,.1,"closure",road="edge:11:12:0",duration_min=10)))
    detours=[e for e in sim.routing_trace if e["type"]=="active_route" and e["detour_minutes"]>0]
    assert detours and all([11,12,0] not in e["route"]["edge_path"] for e in detours)
    assert result.state.orders_completed==1
    assert result.state.distance_traveled_km>.4
    assert result.state.current_node==12
    updates=selected(result,"position_update")
    commitments=[e["commitments"][0]["estimated_completion_time"] for e in updates if e["commitments"]]
    assert len(set(commitments))>1


def test_rain_expires_during_active_travel(store):
    cfg,base=simulator(RoutePlanner(store))
    clean=base.run(stream(cfg,offer(cfg,zone_dropoff=12)))
    _,wet=simulator(RoutePlanner(store))
    rainy=wet.run(stream(cfg,offer(cfg,zone_dropoff=12),shock(cfg,.1,"rain",duration_min=.2)))
    assert rainy.state.distance_traveled_km==pytest.approx(clean.state.distance_traveled_km)
    assert rainy.state.continuous_riding_min>clean.state.continuous_riding_min
    assert wet.world.rain_factor==1
    assert rainy.state.orders_completed==1


def test_multiple_stops_and_delay_keep_geometry_consistent(planner):
    cfg,sim=simulator(planner)
    result=sim.run(stream(cfg,offer(cfg,zone_dropoff=11),offer(cfg,at=.1,order_id="TWO",zone_pickup=10,zone_dropoff=12),
        shock(cfg,.2,"delay",order_id="ONE",slip_min=1)))
    assert result.state.orders_completed==2
    assert result.state.safety_violations==0
    assert sim.state.current_node==sim.planner.store.node(sim.state.current_zone)


class LocalService:
    def __init__(self,planner,directory):
        self.planner,self.directory=planner,directory
    def close(self):
        pass
    async def call(self,operation,payload):
        now=payload.pop("sim_time")
        if operation=="compare":
            return {a:self.planner.route(**payload,algorithm=a,now=now) for a in ("astar","dijkstra")}
        return self.planner.route(**payload,now=now)


def test_api_routes_zones_validation_and_saved_simulation(planner,tmp_path):
    app=create_app(routing_service=LocalService(planner,tmp_path),geospatial_runs=tmp_path)
    with TestClient(app) as client:
        assert len(client.get("/geospatial/zones").json()["features"])==12
        assert client.get("/geospatial/graph/status").json()["cached"] is False
        data={"origin_zone":7,"destination_zone":11}
        assert client.post("/routing/route",json=data).status_code==200
        assert set(client.post("/routing/compare",json=data).json())=={"astar","dijkstra"}
        assert client.post("/routing/route",json={**data,"origin_zone":99}).status_code==422
        assert client.get("/simulation/missing/routes").status_code==404
        folder=tmp_path/"example"
        folder.mkdir()
        (folder/"routes.json").write_text(json.dumps({"agents":{"smart":{"routes":[]}}}))
        assert client.get("/simulation/example/agents/smart/route").status_code==200


def test_api_without_graph_is_explicit_503(tmp_path):
    from app.geospatial.service import RoutingService
    with TestClient(create_app(routing_service=RoutingService(tmp_path))) as client:
        assert client.post("/routing/route",json={"origin_zone":7,"destination_zone":11}).status_code==503


def test_active_no_route_holds_until_closure_expires(planner):
    cfg,sim=simulator(planner)
    # All access roads closed while courier occupies the shortcut, so it must wait.
    result=sim.run(stream(cfg,offer(cfg,zone_dropoff=12),shock(cfg,.1,"closure",road="Access Road",duration_min=2)))
    assert any(e.get("action")=="route_unreachable" for e in selected(result,"position_update"))
    assert result.state.orders_completed==1 and result.state.safety_violations==0
    assert result.state.current_node==12


def test_variable_edge_speeds_account_exact_distance(store):
    graph=nx.MultiDiGraph(store.graph)
    graph[11][12][0]["speed_kph"]=10
    revised=GraphStore(graph,store.zones,store.metadata,store.snaps)
    cfg,sim=simulator(RoutePlanner(revised))
    result=sim.run(stream(cfg,offer(cfg,zone_dropoff=12),shock(cfg,.8,"rain",duration_min=.1)))
    assert result.state.orders_completed==1
    assert result.state.distance_traveled_km==pytest.approx(.4)
    assert result.state.operating_costs==pytest.approx(.4*sim.agent.snapshot.vehicle_profiles["moto"].operating_cost_mxn_per_km)


def test_same_node_route_has_valid_zero_geometry(planner):
    route=planner.route(7,7)
    assert route["eta_min"]==0 and route["distance_km"]==0
    assert len(route["geometry"]["coordinates"])==2


def test_coordinate_routing_bounds(planner):
    route=planner.route_coordinates((25.65,-100.293),(25.65,-100.289))
    assert route["node_path"]==[7,11]
    with pytest.raises(ValueError):
        planner.route_coordinates((0,0),(25.65,-100.289))


def test_cached_graph_offline_and_corruption(store,tmp_path,monkeypatch):
    import osmnx as ox
    from hashlib import sha256
    path=tmp_path/"monterrey_drive.graphml"
    ox.save_graphml(store.graph,path)
    metadata={**store.metadata,"graph_version":sha256(path.read_bytes()).hexdigest()}
    store.metadata=metadata
    (tmp_path/"metadata.json").write_text(json.dumps(metadata))
    store.save_snaps(tmp_path)
    def forbidden(*a,**k):
        raise AssertionError("Offline cache must never download")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    assert RoutePlanner(GraphStore.load(tmp_path)).route(7,11)["distance_km"]==.3
    path.write_text("corrupted")
    with pytest.raises(ValueError,match="checksum"):
        GraphStore.load(tmp_path)


def test_simulation_determinism_with_closure_and_rain(store):
    from app.simulation.replay import logical
    outputs=[]
    for _ in range(2):
        cfg,sim=simulator(RoutePlanner(store))
        result=sim.run(stream(cfg,offer(cfg,zone_dropoff=12),shock(cfg,.1,"closure",road="edge:11:12:0",duration_min=2),
            shock(cfg,.2,"rain",duration_min=.5)))
        outputs.append((logical(result.log.events),sim.routing_trace))
    assert outputs[0]==outputs[1]
