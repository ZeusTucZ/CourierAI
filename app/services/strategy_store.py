from threading import Lock

from app.models.strategy import StrategySnapshot


class StrategyStore:
    def __init__(self, snapshot: StrategySnapshot):
        self._snapshot = snapshot
        self._lock = Lock()

    def get(self) -> StrategySnapshot:
        with self._lock:
            return self._snapshot

    def replace(self, snapshot: StrategySnapshot) -> None:
        # Revalidate even if the caller used Pydantic's unvalidated model_copy.
        validated = StrategySnapshot.model_validate(snapshot.model_dump(mode="json"))
        with self._lock:
            self._snapshot = validated
