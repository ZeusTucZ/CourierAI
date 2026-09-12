from dataclasses import dataclass
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.logging.event_log import encode_events, read_events
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig
from app.simulation.simulator import Simulator


def logical(value):
    if isinstance(value, dict):
        return {key: logical(item) for key, item in value.items()
                if key not in {"latency_ms", "mean_decision_latency_ms", "p95_decision_latency_ms"}}
    if isinstance(value, list):
        return [logical(item) for item in value]
    return value


def recorded_agent(name: str, snapshot: StrategySnapshot):
    if name == "SmartAgent":
        return SmartAgent(snapshot)
    if name == "GreedyRateBaseline":
        agent = GreedyRateBaseline(snapshot)
        # Snapshot is already the recorded baseline strategy, including version.
        agent.snapshot = snapshot
        return agent
    raise ValueError(f"Unsupported recorded agent: {name}")


@dataclass(frozen=True)
class ReplayResult:
    agent_name: str
    decisions_checked: int
    full_execution_matches: bool
    stream_sha256: str


def replay_shift(path: Path) -> ReplayResult:
    events = read_events(path)
    if not events or events[0]["event"] != "shift_start" or events[-1]["event"] != "shift_end":
        raise ValueError("Replay requires a complete shift")
    metadata = events[0]
    if metadata.get("simulator_version") == "mvp3-v1":
        return replay_strategic(events)
    if metadata.get("simulator_version") != "mvp2-v1":
        raise ValueError("Log lacks compatible MVP 2 replay metadata")
    snapshot = StrategySnapshot.model_validate(metadata["strategy_snapshot"])
    name = metadata["agent_name"]
    agent = recorded_agent(name, snapshot)
    decisions = [event for event in events if event["event"] == "decision"]
    for recorded in decisions:
        request = DecideRequest.model_validate(recorded["decision_request"])
        actual = agent.decide_request(request).model_dump(mode="json")
        for key in ("order_id", "decision", "binding_constraint", "reason", "economics", "degraded", "tier"):
            if actual.get(key) != recorded.get(key):
                raise ValueError(f"Replay mismatch for {recorded['order_id']}: {key}")
    stream = [event["source_event"] for event in events if "source_event" in event]
    digest = sha256(encode_events(stream)).hexdigest()
    if digest != metadata["stream_sha256"]:
        raise ValueError("Recorded source stream hash mismatch")
    config = ShiftConfig.model_validate(metadata["simulation_config"])
    result = Simulator(config, recorded_agent(name, snapshot)).run(stream)
    if logical(normalize_mvp2_metadata(result.log.events)) != logical(normalize_mvp2_metadata(events)):
        raise ValueError("Full execution replay differs: inputs, state, events or accounting changed")
    return ReplayResult(name, len(decisions), True, digest)


def normalize_mvp2_metadata(events):
    """Fill only newly added model defaults when reading pre-MVP 3 metadata.

    No recorded decision, input, economics, state or accounting is discarded.
    """
    normalized = deepcopy(events)
    metadata = normalized[0]
    metadata["simulation_config"] = ShiftConfig.model_validate(metadata["simulation_config"]).model_dump(mode="json")
    metadata["strategy_snapshot"] = StrategySnapshot.model_validate(metadata["strategy_snapshot"]).model_dump(mode="json")
    return normalized


def replay_strategic(events):
    from app.simulation.strategic import StrategicSimulator
    from app.strategy.historical import HistoricalDemandModel
    from app.strategy.models import StrategyPolicy
    metadata = events[0]
    stream = [event["source_event"] for event in events if "source_event" in event]
    digest = sha256(encode_events(stream)).hexdigest()
    if digest != metadata["stream_sha256"]:
        raise ValueError("Recorded source stream hash mismatch")
    simulator = StrategicSimulator(ShiftConfig.model_validate(metadata["simulation_config"]),
        recorded_agent(metadata["agent_name"], StrategySnapshot.model_validate(metadata["strategy_snapshot"])),
        HistoricalDemandModel.model_validate(metadata["historical_model"]),
        StrategyPolicy.model_validate(metadata["strategy_policy"]),
        unavailable_updates=metadata["unavailable_updates"])
    actual = simulator.run(stream)
    if logical(actual.log.events) != logical(events):
        raise ValueError("MVP 3 replay mismatch: strategy, decisions, routes or accounting")
    return ReplayResult(metadata["agent_name"], sum(e["event"] == "decision" for e in events), True, digest)
