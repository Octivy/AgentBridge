import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from shared import settings
from shared.schemas import (
    ProductConfigFieldResponse,
    ProductConfigSnapshotResponse,
    ProductConfigValidationIssueResponse,
    ProductConfigValidationResponse,
)


@dataclass(frozen=True)
class ConfigFieldDefinition:
    key: str
    owner: str
    source: str
    category: str
    default_value: str = ""
    sensitive: bool = False
    description: str = ""


BACKEND_CONFIG_FIELDS: tuple[ConfigFieldDefinition, ...] = (
    ConfigFieldDefinition("MINIMAX_BASE_URL", "backend", ".env", "model_provider", settings.MINIMAX_BASE_URL, description="MiniMax OpenAI-compatible endpoint."),
    ConfigFieldDefinition("MINIMAX_API_KEY", "backend", ".env", "model_provider", sensitive=True, description="MiniMax API key."),
    ConfigFieldDefinition("MINIMAX_MODEL", "backend", ".env", "model_provider", settings.MINIMAX_MODEL, description="Default MiniMax model."),
    ConfigFieldDefinition("CADCOPILOT_OFFICIAL_BASE_URL", "backend", ".env", "official_provider", settings.CADCOPILOT_OFFICIAL_BASE_URL, description="AgentBridge official OpenAI-compatible endpoint."),
    ConfigFieldDefinition("CADCOPILOT_OFFICIAL_API_KEY", "backend", ".env", "official_provider", sensitive=True, description="AgentBridge official provider API key."),
    ConfigFieldDefinition("CADCOPILOT_OFFICIAL_MODEL", "backend", ".env", "official_provider", settings.CADCOPILOT_OFFICIAL_MODEL, description="AgentBridge official provider model."),
    ConfigFieldDefinition("OPENAI_BASE_URL", "backend", ".env", "model_provider", settings.OPENAI_BASE_URL, description="OpenAI-compatible endpoint."),
    ConfigFieldDefinition("OPENAI_API_KEY", "backend", ".env", "model_provider", sensitive=True, description="OpenAI API key."),
    ConfigFieldDefinition("OPENAI_MODEL", "backend", ".env", "model_provider", settings.OPENAI_MODEL, description="Default OpenAI model."),
    ConfigFieldDefinition("ANTHROPIC_BASE_URL", "backend", ".env", "model_provider", settings.ANTHROPIC_BASE_URL, description="Anthropic Messages endpoint."),
    ConfigFieldDefinition("ANTHROPIC_API_KEY", "backend", ".env", "model_provider", sensitive=True, description="Anthropic API key."),
    ConfigFieldDefinition("ANTHROPIC_MODEL", "backend", ".env", "model_provider", settings.ANTHROPIC_MODEL, description="Default Anthropic model."),
    ConfigFieldDefinition("DEEPSEEK_BASE_URL", "backend", ".env", "model_provider", settings.DEEPSEEK_BASE_URL, description="DeepSeek OpenAI-compatible endpoint."),
    ConfigFieldDefinition("DEEPSEEK_API_KEY", "backend", ".env", "model_provider", sensitive=True, description="DeepSeek API key."),
    ConfigFieldDefinition("DEEPSEEK_MODEL", "backend", ".env", "model_provider", settings.DEEPSEEK_MODEL, description="Default DeepSeek model."),
    ConfigFieldDefinition("OLLAMA_BASE_URL", "backend", ".env", "model_provider", settings.OLLAMA_BASE_URL, description="Local Ollama OpenAI-compatible endpoint."),
    ConfigFieldDefinition("OLLAMA_MODEL", "backend", ".env", "model_provider", settings.OLLAMA_MODEL, description="Default local Ollama model."),
    ConfigFieldDefinition("SERVICE_TIMEOUT_SECONDS", "backend", ".env", "runtime", str(settings.SERVICE_TIMEOUT_SECONDS), description="Model service timeout in seconds."),
    ConfigFieldDefinition("CADCOPILOT_LOCAL_BRIDGE_URL", "backend", ".env", "local_bridge", settings.CADCOPILOT_LOCAL_BRIDGE_URL, description="Backend to AutoCAD local bridge URL."),
    ConfigFieldDefinition("CADCOPILOT_LOCAL_BRIDGE_TOKEN", "backend", ".env", "local_bridge", sensitive=True, description="Shared local bridge token."),
    ConfigFieldDefinition("CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS", "backend", ".env", "local_bridge", str(settings.CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS), description="Local bridge timeout in seconds."),
    ConfigFieldDefinition("CADCOPILOT_PLANNER_STORE_PATH", "backend", ".env", "task_history", settings.CADCOPILOT_PLANNER_STORE_PATH, description="Optional JSON file path for planner task persistence."),
    ConfigFieldDefinition("CADCOPILOT_SKILL_DRAFT_STORE_PATH", "backend", ".env", "skills", settings.CADCOPILOT_SKILL_DRAFT_STORE_PATH, description="JSON file path for user Skill drafts awaiting review."),
    ConfigFieldDefinition("CADCOPILOT_KNOWLEDGE_ROOTS", "backend", ".env", "knowledge", settings.CADCOPILOT_KNOWLEDGE_ROOTS, description="Semicolon-separated local folders containing approved company standard documents."),
    ConfigFieldDefinition("CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES", "backend", ".env", "knowledge", str(settings.CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES), description="Maximum bytes read from one local knowledge file."),
    ConfigFieldDefinition("CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS", "backend", ".env", "knowledge", str(settings.CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS), description="Maximum retrieved source characters sent to a model."),
    ConfigFieldDefinition("CADCOPILOT_MODEL_CONFIG_PATH", "backend", ".env", "model_provider", settings.CADCOPILOT_MODEL_CONFIG_PATH, description="Optional JSON file path for model provider configuration persistence."),
    ConfigFieldDefinition("CADCOPILOT_ADMIN_TOKEN", "backend", ".env", "admin", sensitive=True, description="Admin API token for /admin routes."),
    ConfigFieldDefinition("CADCOPILOT_RELEASE_VERSION", "backend", ".env", "release", settings.CADCOPILOT_RELEASE_VERSION, description="Backend release version."),
    ConfigFieldDefinition("CADCOPILOT_SCHEMA_VERSION", "backend", ".env", "release", settings.CADCOPILOT_SCHEMA_VERSION, description="Public API schema version."),
)


PLUGIN_CONFIG_FIELDS: tuple[ConfigFieldDefinition, ...] = (
    ConfigFieldDefinition("CADCOPILOT_CONNECTION_MODE", "plugin", "agentbridge.config.json", "connection", "standard", description="standard or service mode."),
    ConfigFieldDefinition("LLM_PROVIDER", "plugin", "agentbridge.config.json", "model_provider", "minimax", description="Current direct provider selection."),
    ConfigFieldDefinition("OPENAI_API_KEY", "plugin", "agentbridge.config.json", "model_provider", sensitive=True, description="User-owned direct provider API key."),
    ConfigFieldDefinition("OPENAI_API_BASE_URL", "plugin", "agentbridge.config.json", "model_provider", "https://api.minimaxi.com/v1", description="User-owned direct provider endpoint."),
    ConfigFieldDefinition("OPENAI_MODEL", "plugin", "agentbridge.config.json", "model_provider", "MiniMax-M2.7", description="User-owned direct model name."),
    ConfigFieldDefinition("DIRECT_MODEL_PROFILES", "plugin", "agentbridge.config.json", "model_provider", sensitive=True, description="Serialized direct model profiles; may contain keys."),
    ConfigFieldDefinition("ACTIVE_DIRECT_MODEL", "plugin", "agentbridge.config.json", "model_provider", "MiniMax-M2.7", description="Active standard-mode model."),
    ConfigFieldDefinition("SERVICE_MODEL_PROFILES", "plugin", "agentbridge.config.json", "model_provider", "[]", description="Serialized service model profiles."),
    ConfigFieldDefinition("ACTIVE_SERVICE_MODEL", "plugin", "agentbridge.config.json", "model_provider", "MiniMax-M2.7", description="Active service-mode model."),
    ConfigFieldDefinition("CADCOPILOT_MODEL", "plugin", "agentbridge.config.json", "model_provider", "MiniMax-M2.7", description="Backend model requested by plugin."),
    ConfigFieldDefinition("CADCOPILOT_API_BASE_URL", "plugin", "agentbridge.config.json", "connection", "http://127.0.0.1:8000", description="Backend service URL."),
    ConfigFieldDefinition("LOCAL_BRIDGE_ENABLED", "plugin", "agentbridge.config.json", "local_bridge", "true", description="Whether the AutoCAD local tool bridge starts."),
    ConfigFieldDefinition("LOCAL_BRIDGE_HOST", "plugin", "agentbridge.config.json", "local_bridge", "127.0.0.1", description="AutoCAD local tool bridge host."),
    ConfigFieldDefinition("LOCAL_BRIDGE_PORT", "plugin", "agentbridge.config.json", "local_bridge", "8765", description="AutoCAD local tool bridge port."),
    ConfigFieldDefinition("LOCAL_BRIDGE_TOKEN", "plugin", "agentbridge.config.json", "local_bridge", sensitive=True, description="AutoCAD local tool bridge token."),
    ConfigFieldDefinition("LOG_LEVEL", "plugin", "agentbridge.config.json", "diagnostics", "INFO", description="Plugin log level."),
)


def build_product_config_snapshot() -> ProductConfigSnapshotResponse:
    backend_fields = [_build_backend_field(field) for field in BACKEND_CONFIG_FIELDS]
    plugin_fields = [_build_static_field(field) for field in PLUGIN_CONFIG_FIELDS]
    sensitive_keys = sorted({field.key for field in (*BACKEND_CONFIG_FIELDS, *PLUGIN_CONFIG_FIELDS) if field.sensitive})
    return ProductConfigSnapshotResponse(
        backend_fields=backend_fields,
        plugin_fields=plugin_fields,
        sensitive_keys=sensitive_keys,
    )


def validate_product_config() -> ProductConfigValidationResponse:
    issues: list[ProductConfigValidationIssueResponse] = []
    _append_url_issue(issues, "MINIMAX_BASE_URL", settings.MINIMAX_BASE_URL)
    _append_url_issue(issues, "OPENAI_BASE_URL", settings.OPENAI_BASE_URL)
    _append_url_issue(issues, "ANTHROPIC_BASE_URL", settings.ANTHROPIC_BASE_URL)
    _append_url_issue(issues, "DEEPSEEK_BASE_URL", settings.DEEPSEEK_BASE_URL)
    _append_url_issue(issues, "OLLAMA_BASE_URL", settings.OLLAMA_BASE_URL)
    _append_url_issue(issues, "CADCOPILOT_LOCAL_BRIDGE_URL", settings.CADCOPILOT_LOCAL_BRIDGE_URL)
    _append_positive_number_issue(issues, "SERVICE_TIMEOUT_SECONDS", settings.SERVICE_TIMEOUT_SECONDS)
    _append_positive_number_issue(issues, "CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS", settings.CADCOPILOT_LOCAL_BRIDGE_TIMEOUT_SECONDS)
    _append_positive_number_issue(issues, "CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES", settings.CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES)
    _append_positive_number_issue(issues, "CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS", settings.CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS)

    if not any((settings.MINIMAX_API_KEY, settings.OPENAI_API_KEY, settings.DEEPSEEK_API_KEY)):
        issues.append(
            ProductConfigValidationIssueResponse(
                key="MODEL_PROVIDER_API_KEY",
                owner="backend",
                severity="warning",
                message="未检测到 backend provider API key；标准聊天或 planner 调用外部模型时可能失败。",
            )
        )

    return ProductConfigValidationResponse(
        ok=not any(issue.severity == "error" for issue in issues),
        issues=issues,
    )


def _build_backend_field(field: ConfigFieldDefinition) -> ProductConfigFieldResponse:
    env_value = os.getenv(field.key)
    runtime_value = _runtime_setting_value(field.key, field.default_value)
    configured = bool((env_value if env_value is not None else runtime_value or "").strip())
    return _to_response(field, configured=configured, value=runtime_value)


def _build_static_field(field: ConfigFieldDefinition) -> ProductConfigFieldResponse:
    return _to_response(field, configured=bool((field.default_value or "").strip()), value=field.default_value)


def _to_response(field: ConfigFieldDefinition, *, configured: bool, value: Optional[str]) -> ProductConfigFieldResponse:
    return ProductConfigFieldResponse(
        key=field.key,
        owner=field.owner,
        source=field.source,
        category=field.category,
        configured=configured,
        sensitive=field.sensitive,
        value=None if field.sensitive else value,
        description=field.description,
    )


def _runtime_setting_value(key: str, default_value: str) -> str:
    value = getattr(settings, key, default_value)
    return str(value if value is not None else "")


def _append_url_issue(issues: list[ProductConfigValidationIssueResponse], key: str, value: str) -> None:
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        issues.append(
            ProductConfigValidationIssueResponse(
                key=key,
                owner="backend",
                severity="error",
                message=f"{key} 必须是 http(s) URL。",
            )
        )


def _append_positive_number_issue(issues: list[ProductConfigValidationIssueResponse], key: str, value: float) -> None:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = 0

    if numeric_value <= 0:
        issues.append(
            ProductConfigValidationIssueResponse(
                key=key,
                owner="backend",
                severity="error",
                message=f"{key} 必须大于 0。",
            )
        )
