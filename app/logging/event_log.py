import json
from copy import deepcopy
from pathlib import Path

from app.simulation.events import Event, PUBLIC_EVENTS, event_time


def encode_events(events: list[Event] | tuple[Event, ...]) -> bytes:
    return ("".join(json.dumps(event, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False) + "\n"
                    for event in events)).encode("utf-8")


class EventLog:
    def __init__(self):
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        if event["event"] not in PUBLIC_EVENTS:
            raise ValueError("Unknown public event type")
        if self.events and event_time(event) < event_time(self.events[-1]):
            raise ValueError("Event log must be chronological")
        self.events.append(deepcopy(event))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encode_events(self.events))


def read_events(path: Path) -> list[Event]:
    log = EventLog()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            log.append(json.loads(line))
    return log.events
