from dataclasses import dataclass
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
    if logical(result.log.events) != logical(events):
        raise ValueError("Full execution replay differs: inputs, state, events or accounting changed")
    return ReplayResult(name, len(decisions), True, digest)
