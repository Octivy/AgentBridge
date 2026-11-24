from contextlib import asynccontextmanager
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from http_api.routes import router
from product.model_config_service import get_runtime_model_provider_config
from connector_runtime.diagnostics import build_connector_capabilities
from shared.settings import CADCOPILOT_RELEASE_VERSION, CADCOPILOT_SCHEMA_VERSION, MINIMAX_MODEL
from host_config.heal import bridge_supervisor


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Keep auto_start bridges alive for the lifetime of the backend process.
    bridge_supervisor.start()
    yield
    bridge_supervisor.stop()


app = FastAPI(title="AgentBridge Backend", version=CADCOPILOT_RELEASE_VERSION, lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface the real error in the panel instead of a bare 500 (loopback app)."""

    logging.getLogger("uvicorn.error").error(
        "Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {type(exc).__name__}: {exc}"},
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    runtime_provider = get_runtime_model_provider_config()
    return {
        "status": "ok",
        "version": CADCOPILOT_RELEASE_VERSION,
        "schema_version": CADCOPILOT_SCHEMA_VERSION,
        "provider": runtime_provider.provider if runtime_provider else "minimax",
        "model": runtime_provider.model if runtime_provider else MINIMAX_MODEL,
        "mcp_server": "cadmcp",
        "connector": build_connector_capabilities(),
    }


app.include_router(router)


__all__ = ["app"]
