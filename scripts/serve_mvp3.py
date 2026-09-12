"""Serve a precomputed snapshot: uvicorn scripts.serve_mvp3:app.

Generate artifacts/strategy_snapshot.json using benchmark_mvp3 or export a
StrategyUpdater result. Disk is read once on startup, never from /decide.
"""
from pathlib import Path

from app.main import create_app
from app.models.strategy import StrategySnapshot

app = create_app(StrategySnapshot.model_validate_json(Path("artifacts/strategy_snapshot.json").read_text()))
