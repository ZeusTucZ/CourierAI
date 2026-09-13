"""Separate demonstration artifacts; never writes tuning or held-out results."""
import argparse
import json
from pathlib import Path
from app.agents.nearby import FirstNearbyOrderBaseline, FirstNearbyBaselineConfig
from app.agents.smart import SmartAgent
from app.models.strategy import StrategySnapshot
from app.evaluation.freeze import load_frozen
from app.simulation.config import ShiftConfig
from app.simulation.generator import generate_shift
from app.simulation.strategic import StrategicSimulator
from app.geospatial.simulation import GeospatialSimulator
from app.geospatial.graph import GraphStore
from app.geospatial.routing import RoutePlanner
from app.logging.event_log import encode_events


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--routing",choices=("osm","precomputed"),default="osm")
    parser.add_argument("--seed",type=int,default=202635)
    parser.add_argument("--shift-hours",type=float,default=4)
    parser.add_argument("--vehicle",choices=("moto","car","bike"),default="moto")
    parser.add_argument("--frozen",type=Path,help="Existing frozen MVP 3 file; read and verify only")
    args=parser.parse_args()
    frozen=args.frozen or Path("artifacts/final_strategy_config.json")
    if frozen.exists() or args.frozen:
        profile,model,policy=load_frozen(frozen)
        configuration_source=str(frozen)
    else:
        from app.strategy.historical import HistoricalDemandModel
        from app.strategy.models import StrategyPolicy
        profile,model,policy=None,HistoricalDemandModel(),StrategyPolicy()
        configuration_source="Existing built-in defaults; frozen artifact absent; geographic smoke only, no calibration claim"
    print(configuration_source)
    cfg=ShiftConfig(seed=args.seed,shift_hours=args.shift_hours,vehicle=args.vehicle,start_location_zone=7,profile=profile)
    source=generate_shift(cfg)
    store=GraphStore.load() if args.routing=="osm" else None
    snapshot=StrategySnapshot(reservation_wage_mxn_hr=policy.base_reservation_wage,zone_values={})
    simulation_id=f"{args.routing}-seed-{args.seed}"
    output=Path("artifacts/geospatial/runs")/simulation_id
    if output.exists():
        raise ValueError("Demo ID already exists; choose a new seed or inspect the existing artifacts")
    output.mkdir(parents=True)
    document={"simulation_id":simulation_id,"routing_source":args.routing,"configuration_source":configuration_source,"agents":{}}
    for agent in (FirstNearbyOrderBaseline(FirstNearbyBaselineConfig.load(),snapshot),SmartAgent(snapshot)):
        # Same existing baseline-only flags used by run_pair_v3, without touching frozen policy.
        agent_policy=policy.model_copy(update={"use_zone_value":False,"use_reposition":False,"use_improved_batching":False,
            "use_historical_prediction":False,"use_cancellation":False}) if isinstance(agent,FirstNearbyOrderBaseline) else policy
        simulator=GeospatialSimulator(cfg,agent,model,agent_policy,RoutePlanner(store,agent.snapshot.vehicle_profiles)) if store else StrategicSimulator(cfg,agent,model,agent_policy)
        result=simulator.run(source)
        result.log.write(output/f"{agent.name}.jsonl")
        (output/f"{agent.name}.trace.jsonl").write_bytes(encode_events(simulator.trace))
        traces=getattr(simulator,"routing_trace",[])
        (output/f"{agent.name}.routing.jsonl").write_bytes(encode_events(traces))
        document["agents"][agent.name]={"metrics":result.metrics.to_dict(),"current_zone":result.state.current_zone,
            "current_node":getattr(result.state,"current_node",None),"routes":traces,
            "closures":simulator.planner.closures.geojson(result.state.current_sim_time) if store else None}
        print(agent.name,json.dumps(result.metrics.to_dict()))
    (output/"source.jsonl").write_bytes(encode_events(source))
    (output/"routes.json").write_text(json.dumps(document,indent=2),encoding="utf-8")
    print("simulation_id:",simulation_id)


if __name__=="__main__":
    main()
