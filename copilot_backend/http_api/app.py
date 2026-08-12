from typing import Any, Dict

from fastapi import FastAPI

from http_api.routes import router
from product.model_config_service import get_runtime_model_provider_config
from connector_runtime.diagnostics import build_connector_capabilities
from shared.settings import CADCOPILOT_RELEASE_VERSION, CADCOPILOT_SCHEMA_VERSION, MINIMAX_MODEL


app = FastAPI(title="AgentBridge Backend", version=CADCOPILOT_RELEASE_VERSION)


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
