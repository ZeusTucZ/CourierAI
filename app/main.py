from time import perf_counter_ns

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.decision.engine import DecisionService
from app.logging.decision_log import DecisionLog
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore


def create_app(snapshot: StrategySnapshot | None = None) -> FastAPI:
    application = FastAPI(title="Courier Fast Decision Engine", version="0.1.0")
    application.state.decisions = DecisionService(
        StrategyStore(snapshot or StrategySnapshot()), DecisionLog(),
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Do not echo NaN/Infinity or exception objects into a JSON error response.
        return JSONResponse(status_code=422, content={"detail": [
            {key: error[key] for key in ("type", "loc", "msg")}
            for error in exc.errors()
        ]})

    @application.middleware("http")
    async def measure_start(request: Request, call_next):
        request.state.started_ns = perf_counter_ns()
        return await call_next(request)

    application.include_router(router)
    return application


app = create_app()
