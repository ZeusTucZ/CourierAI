from copy import deepcopy
from threading import Lock
from time import perf_counter_ns

from app.models.responses import DecisionRecord


class DecisionLog:
    """Process-local append-only history; lookup returns the latest occurrence.

    Records survive snapshot replacement, not process restart. No disk I/O.
    """

    def __init__(self):
        self._records: dict[str, list[DecisionRecord]] = {}
        self._lock = Lock()

    def append(self, record: DecisionRecord, started_ns: int) -> float:
        detached = deepcopy(record)
        with self._lock:
            records = self._records.setdefault(record.order_id, [])
            records.append(detached)
            latency = (perf_counter_ns() - started_ns) / 1_000_000
            records[-1] = detached.model_copy(update={"latency_ms": latency})
        return latency

    def get(self, order_id: str) -> DecisionRecord | None:
        with self._lock:
            records = self._records.get(order_id)
            return deepcopy(records[-1]) if records else None

    def history(self, order_id: str) -> tuple[DecisionRecord, ...]:
        with self._lock:
            return tuple(deepcopy(self._records.get(order_id, ())))
