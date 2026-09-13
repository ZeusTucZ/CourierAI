from time import perf_counter_ns
from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.decision.engine import DecisionService
from app.logging.decision_log import DecisionLog
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore


def create_app(snapshot: StrategySnapshot | None = None, *, routing_service=None, geospatial_runs=None, demo_service=None, advisor=None) -> FastAPI:
    from app.geospatial.api import router as geographic_router
    from app.geospatial.service import RoutingService
    from app.geospatial.zones import ROOT
    from app.demo.api import router as demo_router
    from app.demo.speech import router as speech_router
    from app.demo.service import DemoService

    @asynccontextmanager
    async def lifespan(application):
        yield
        await application.state.demo.close()
        application.state.routing.close()

    application = FastAPI(title="Courier Fast Decision Engine", version="0.1.0", lifespan=lifespan)
    # Comma-separated public frontend origins. Keep local Vite development
    # working without opening the API to every website in production.
    cors_origins = [origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.routing = routing_service or RoutingService(ROOT / "data/osm")
    application.state.demo = demo_service or DemoService()
    application.state.geospatial_runs = Path(geospatial_runs or ROOT / "artifacts/geospatial/runs")
    if advisor is None:
        from app.llm.gemini_client import GeminiClient, GeminiConfig
        from app.llm.strategy_advisor import GeminiStrategyAdvisor
        gemini_config = GeminiConfig.from_env()
        if gemini_config.enabled:
            advisor = GeminiStrategyAdvisor(GeminiClient(gemini_config), gemini_config)
    application.state.decisions = DecisionService(
        StrategyStore(snapshot or StrategySnapshot()), DecisionLog(), advisor,
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
    application.include_router(geographic_router)
    application.include_router(demo_router)
    application.include_router(speech_router)

    @application.get("/healthz", include_in_schema=False)
    async def healthcheck():
        return {"status": "ok"}

    return application


app = create_app()
