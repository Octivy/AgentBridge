from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from cadmcp.cad_bridge_client import CadBridgeError, CadLocalBridgeClient
from cadmcp.tool_registry import PRODUCT_MVP_TOOL_NAMES
from gateway.provider_client import call_provider
from shared import settings
from shared.schemas import ChatMessageRequest


STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"
STATUS_WARNING = "warning"


@dataclass
class AcceptanceCheck:
    check_id: str
    name: str
    status: str
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    recovery_action: str = ""


@dataclass
class AcceptanceReport:
    schema_version: str
    generated_at: str
    status: str
    checks: list[AcceptanceCheck]
    environment: dict[str, Any]
    secrets_redacted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConnectorAcceptanceRunner:
    def __init__(
        self,
        root: Path,
        *,
        mcp_repeat: int = 20,
        provider_repeat: int = 10,
        bridge_repeat: int = 20,
        provider: str = "auto",
        provider_caller: Callable[..., Awaitable[str]] = call_provider,
    ):
        self.root = root.resolve()
        self.mcp_repeat = max(1, mcp_repeat)
        self.provider_repeat = max(1, provider_repeat)
        self.bridge_repeat = max(1, bridge_repeat)
        self.provider = provider
        self._provider_caller = provider_caller

    async def run(self) -> AcceptanceReport:
        environment = detect_environment(self.root)
        checks = [
            self._check_static_contract(environment),
            self._check_second_host(environment),
            await self._check_backend_diagnostics(environment),
            await self._check_mcp_stability(),
            await self._check_provider_stability(),
            await self._check_bridge_stability(environment),
        ]
        statuses = {item.status for item in checks}
        overall = STATUS_FAILED if STATUS_FAILED in statuses else STATUS_BLOCKED if STATUS_BLOCKED in statuses else STATUS_WARNING if STATUS_WARNING in statuses else STATUS_PASSED
        return AcceptanceReport(
            schema_version="1.0",
            generated_at=datetime.now(timezone.utc).isoformat(),
            status=overall,
            checks=checks,
            environment=environment,
        )

    async def _check_backend_diagnostics(self, environment: dict[str, Any]) -> AcceptanceCheck:
        if not environment["backend_port_open"]:
            return AcceptanceCheck(
                check_id="backend_diagnostics",
                name="Backend five-layer diagnostics",
                status=STATUS_BLOCKED,
                summary="Backend port 8000 is not listening.",
                recovery_action="Start the backend with start-local-dev.ps1 and rerun acceptance.",
            )
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get("http://127.0.0.1:8000/connector/diagnostics")
            response.raise_for_status()
            payload = response.json()
            components = payload.get("components", []) if isinstance(payload, dict) else []
            component_ids = {item.get("id") for item in components if isinstance(item, dict)}
            expected = {"backend", "mcp", "model_gateway", "local_bridge", "autocad"}
            missing = sorted(expected - component_ids)
            overall = str(payload.get("status") or "unknown")
            ok = not missing and overall in {"ok", "degraded"}
            return AcceptanceCheck(
                check_id="backend_diagnostics",
                name="Backend five-layer diagnostics",
                status=STATUS_PASSED if ok else STATUS_FAILED,
                summary=f"Backend returned {len(components)} diagnostic components with overall status {overall}.",
                metrics={"overall_status": overall, "component_ids": sorted(component_ids), "missing": missing},
                recovery_action="Inspect /connector/diagnostics component errors and bridge token synchronization." if not ok else "",
            )
        except Exception as exc:
            return AcceptanceCheck(
                check_id="backend_diagnostics",
                name="Backend five-layer diagnostics",
                status=STATUS_FAILED,
                summary="Backend diagnostics request failed.",
                metrics={"error_category": classify_error(exc), "error": safe_error(exc)},
                recovery_action="Restart backend and verify its inherited local bridge token.",
            )

    def _check_static_contract(self, environment: dict[str, Any]) -> AcceptanceCheck:
        codex_config = self.root / ".codex" / "config.toml"
        script = self.root / "scripts" / "start-cadmcp.ps1"
        config_text = codex_config.read_text(encoding="utf-8") if codex_config.exists() else ""
        markers = ("[mcp_servers.cadmcp]", "scripts/start-cadmcp.ps1", 'default_tools_approval_mode = "writes"')
        missing = [marker for marker in markers if marker not in config_text]
        if not script.exists():
            missing.append("scripts/start-cadmcp.ps1")
        return AcceptanceCheck(
            check_id="host_contract",
            name="Codex / MCP Host contract",
            status=STATUS_PASSED if not missing else STATUS_FAILED,
            summary="Project-scoped Codex configuration and write approval policy are present." if not missing else "MCP Host configuration is incomplete.",
            metrics={"missing_markers": missing, "codex_available": environment["codex_available"]},
            recovery_action="Restore .codex/config.toml and scripts/start-cadmcp.ps1." if missing else "",
        )

    def _check_second_host(self, environment: dict[str, Any]) -> AcceptanceCheck:
        available = environment["claude_host_available"]
        configured = environment["claude_mcp_configured"]
        connected = environment["claude_mcp_status"] == "connected"
        return AcceptanceCheck(
            check_id="second_host",
            name="Second MCP Host",
            status=STATUS_PASSED if connected else STATUS_BLOCKED,
            summary=(
                "Claude Code has an approved, connected project-level cadmcp server."
                if connected
                else "Claude Code is installed and project configuration exists, but its project MCP approval/connection is not complete."
                if available and configured
                else "No configured Claude-compatible second Host was detected."
            ),
            metrics={
                "claude_host_available": available,
                "claude_mcp_configured": configured,
                "claude_mcp_status": environment["claude_mcp_status"],
            },
            recovery_action=(
                "Open Claude Code in this project, approve the project cadmcp server, verify it is connected, then rerun acceptance."
                if available and configured and not connected
                else "Install Claude Code and register the project cadmcp server."
                if not connected
                else ""
            ),
        )

    async def _check_mcp_stability(self) -> AcceptanceCheck:
        attempts: list[dict[str, Any]] = []
        for index in range(self.mcp_repeat):
            started = time.perf_counter()
            try:
                server_name, names = await _one_mcp_handshake(self.root)
                drift = sorted(set(names) ^ set(PRODUCT_MVP_TOOL_NAMES))
                ok = not drift and len(names) == len(PRODUCT_MVP_TOOL_NAMES)
                attempts.append(
                    {
                        "attempt": index + 1,
                        "ok": ok,
                        "latency_ms": _elapsed_ms(started),
                        "server": server_name,
                        "tool_count": len(names),
                        "tool_drift": drift,
                    }
                )
            except Exception as exc:
                attempts.append(
                    {
                        "attempt": index + 1,
                        "ok": False,
                        "latency_ms": _elapsed_ms(started),
                        "error_category": classify_error(exc),
                        "error": safe_error(exc),
                    }
                )
        successes = sum(1 for item in attempts if item["ok"])
        rate = successes / self.mcp_repeat
        return AcceptanceCheck(
            check_id="mcp_stability",
            name="CADMCP repeated initialization and discovery",
            status=STATUS_PASSED if rate >= 0.95 else STATUS_FAILED,
            summary=f"{successes}/{self.mcp_repeat} MCP sessions initialized with the exact {len(PRODUCT_MVP_TOOL_NAMES)}-tool contract.",
            metrics={
                "planned_attempts": self.mcp_repeat,
                "successful_attempts": successes,
                "success_rate": round(rate, 4),
                "attempts": attempts,
            },
            recovery_action="Inspect MCP stderr, Python environment and product tool registry drift." if rate < 0.95 else "",
        )

    async def _check_provider_stability(self) -> AcceptanceCheck:
        provider = resolve_online_provider(self.provider)
        if provider is None:
            return AcceptanceCheck(
                check_id="provider_stability",
                name="Online model provider",
                status=STATUS_BLOCKED,
                summary="No callable provider configuration was detected.",
                metrics={"planned_attempts": self.provider_repeat, "configured_provider": None},
                recovery_action="Configure one provider API key or start Ollama, then rerun acceptance.",
            )

        attempts: list[dict[str, Any]] = []
        terminal_error = False
        for index in range(self.provider_repeat):
            started = time.perf_counter()
            request = ChatMessageRequest(
                message="Reply with exactly OK.",
                provider=provider,
                mode="chat",
            )
            try:
                result = await self._provider_caller(request)
                normalized = (result or "").strip()
                attempts.append(
                    {
                        "attempt": index + 1,
                        "ok": bool(normalized),
                        "latency_ms": _elapsed_ms(started),
                        "response_length": len(normalized),
                        "response_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16],
                    }
                )
            except Exception as exc:
                category = classify_error(exc)
                terminal_error = category in {"authentication", "configuration"}
                attempts.append(
                    {
                        "attempt": index + 1,
                        "ok": False,
                        "latency_ms": _elapsed_ms(started),
                        "error_category": category,
                        "error": safe_error(exc),
                    }
                )
                if terminal_error:
                    break
        successes = sum(1 for item in attempts if item["ok"])
        rate = successes / self.provider_repeat
        status = STATUS_PASSED if rate >= 0.95 else STATUS_FAILED
        summary = f"{successes}/{self.provider_repeat} planned {provider} requests succeeded."
        if terminal_error:
            summary += " Remaining calls were skipped after a non-transient credential/configuration error."
        return AcceptanceCheck(
            check_id="provider_stability",
            name="Online model provider",
            status=status,
            summary=summary,
            metrics={
                "configured_provider": provider,
                "planned_attempts": self.provider_repeat,
                "attempted": len(attempts),
                "successful_attempts": successes,
                "success_rate": round(rate, 4),
                "attempts": attempts,
            },
            recovery_action="Replace or authorize the configured provider credential, then rerun the 10-call gate." if status == STATUS_FAILED else "",
        )

    async def _check_bridge_stability(self, environment: dict[str, Any]) -> AcceptanceCheck:
        if not environment["bridge_port_open"]:
            return AcceptanceCheck(
                check_id="bridge_stability",
                name="AutoCAD local bridge",
                status=STATUS_BLOCKED,
                summary="AutoCAD local bridge port is not listening.",
                metrics={"planned_attempts": self.bridge_repeat, "attempted": 0, "autocad_running": environment["autocad_running"]},
                recovery_action="Start AutoCAD 2024, load AgentBridge, open a DWG and rerun acceptance.",
            )
        attempts: list[dict[str, Any]] = []
        client = CadLocalBridgeClient(token=_installed_bridge_token(), timeout_seconds=5)
        for index in range(self.bridge_repeat):
            started = time.perf_counter()
            try:
                health = await client.health()
                result = health.get("result", {}) if isinstance(health, dict) else {}
                autocad = result.get("autocad", {}) if isinstance(result, dict) else {}
                document_open = bool(autocad.get("document_open"))
                if not document_open:
                    attempts.append(
                        {
                            "attempt": index + 1,
                            "ok": False,
                            "latency_ms": _elapsed_ms(started),
                            "document_open": False,
                            "error_category": "no_active_document",
                            "error": "Bridge is healthy, but AutoCAD has no active drawing.",
                        }
                    )
                    continue
                snapshot = await client.execute_tool(
                    "get_drawing_snapshot",
                    {},
                    caller="connector_acceptance",
                    timeout_ms=5000,
                    dry_run=False,
                )
                snapshot_ok = bool(snapshot.get("ok")) if isinstance(snapshot, dict) else False
                attempts.append(
                    {
                        "attempt": index + 1,
                        "ok": snapshot_ok,
                        "latency_ms": _elapsed_ms(started),
                        "document_open": True,
                        "snapshot_read": snapshot_ok,
                    }
                )
            except CadBridgeError as exc:
                attempts.append(
                    {
                        "attempt": index + 1,
                        "ok": False,
                        "latency_ms": _elapsed_ms(started),
                        "error_category": classify_error(exc),
                        "error": safe_error(exc),
                    }
                )
        successes = sum(1 for item in attempts if item["ok"])
        rate = successes / self.bridge_repeat
        return AcceptanceCheck(
            check_id="bridge_stability",
            name="AutoCAD local bridge",
            status=STATUS_PASSED if rate >= 0.95 else STATUS_FAILED,
            summary=f"{successes}/{self.bridge_repeat} bridge health and drawing snapshot reads succeeded.",
            metrics={
                "planned_attempts": self.bridge_repeat,
                "successful_attempts": successes,
                "success_rate": round(rate, 4),
                "attempts": attempts,
            },
            recovery_action="Inspect bridge URL/token, AutoCAD responsiveness and protocol version." if rate < 0.95 else "",
        )


async def _one_mcp_handshake(root: Path) -> tuple[str, list[str]]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cadmcp"],
        cwd=str(root),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            result = await session.initialize()
            tools = await session.list_tools()
            return result.serverInfo.name, sorted(tool.name for tool in tools.tools)


def detect_environment(root: Path) -> dict[str, Any]:
    claude_status = _claude_mcp_status(root)
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "autocad_running": _process_running("acad.exe"),
        "backend_port_open": _port_open(8000),
        "bridge_port_open": _port_open(8765),
        "ollama_port_open": _port_open(11434),
        "codex_available": bool(shutil.which("codex")) or (root / ".codex" / "config.toml").exists(),
        "claude_host_available": bool(shutil.which("claude")) or _claude_desktop_exists(),
        "claude_mcp_configured": (root / ".mcp.json").exists(),
        "claude_mcp_status": claude_status,
        "provider_configuration": {
            "minimax": bool(settings.MINIMAX_API_KEY),
            "openai": bool(settings.OPENAI_API_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
            "deepseek": bool(settings.DEEPSEEK_API_KEY),
            "ollama": _port_open(11434),
        },
    }


def resolve_online_provider(requested: str) -> Optional[str]:
    normalized = (requested or "auto").strip().lower()
    configured = {
        "minimax": bool(settings.MINIMAX_API_KEY),
        "openai": bool(settings.OPENAI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "deepseek": bool(settings.DEEPSEEK_API_KEY),
        "ollama": _port_open(11434),
    }
    if normalized != "auto":
        return normalized if configured.get(normalized, False) else None
    for provider in ("openai", "anthropic", "deepseek", "minimax", "ollama"):
        if configured[provider]:
            return provider
    return None


def classify_error(exc: Exception) -> str:
    value = safe_error(exc).lower()
    if any(marker in value for marker in ("api key", "unauthorized", "401", "403", "authentication")):
        return "authentication"
    if any(marker in value for marker in ("429", "rate limit", "frequency", "quota", "额度", "频率")):
        return "rate_limit"
    if any(marker in value for marker in ("timeout", "timed out")):
        return "timeout"
    if any(marker in value for marker in ("not configured", "不能为空", "unsupported", "不支持")):
        return "configuration"
    if any(marker in value for marker in ("connection", "unreachable", "refused", "无法连接")):
        return "unreachable"
    return "provider_or_runtime"


def safe_error(exc: Exception) -> str:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    value = str(detail or exc.__class__.__name__)
    for secret in (
        settings.MINIMAX_API_KEY,
        settings.OPENAI_API_KEY,
        settings.ANTHROPIC_API_KEY,
        settings.DEEPSEEK_API_KEY,
        settings.CADCOPILOT_LOCAL_BRIDGE_TOKEN,
    ):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value[:500]


def write_report(report: AcceptanceReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = report_dir / f"connector-acceptance-{stamp}.json"
    markdown_path = report_dir / f"connector-acceptance-{stamp}.md"
    json_path.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _markdown(report: AcceptanceReport) -> str:
    lines = [
        "# AgentBridge 连接器验收报告",
        "",
        f"- 生成时间：{report.generated_at}",
        f"- 总状态：`{report.status}`",
        f"- 敏感信息已脱敏：`{str(report.secrets_redacted).lower()}`",
        "",
        "## 检查结果",
        "",
        "| 检查 | 状态 | 结论 |",
        "| --- | --- | --- |",
    ]
    for item in report.checks:
        lines.append(f"| {item.name} | `{item.status}` | {item.summary.replace('|', '/')} |")
    lines.extend(["", "## 恢复动作", ""])
    actions = [f"- **{item.name}**：{item.recovery_action}" for item in report.checks if item.recovery_action]
    lines.extend(actions or ["- 无。"])
    lines.extend(["", "## 环境摘要", "", "```json", json.dumps(report.environment, ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _process_running(image_name: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return image_name.lower() in (result.stdout or "").lower()


def _claude_desktop_exists() -> bool:
    candidates = [
        Path.home() / "AppData" / "Local" / "AnthropicClaude" / "Claude.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "claude" / "Claude.exe",
    ]
    return any(path.exists() for path in candidates)


def _installed_bridge_token() -> str:
    app_data = Path.home() / "AppData" / "Roaming"
    config_path = app_data / "Autodesk" / "ApplicationPlugins" / "AgentBridge.bundle" / "Contents" / "agentbridge.config.json"
    if not config_path.exists():
        return ""
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("LOCAL_BRIDGE_TOKEN") or "").strip()


def _claude_mcp_status(root: Path) -> str:
    command = shutil.which("claude.cmd") or shutil.which("claude")
    if not command or not (root / ".mcp.json").exists():
        return "not_configured"
    try:
        result = subprocess.run(
            [command, "mcp", "get", "cadmcp"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    if "connected" in output:
        return "connected"
    if "pending approval" in output:
        return "pending_approval"
    if "failed" in output or "error" in output:
        return "failed"
    return "configured" if result.returncode == 0 else "unknown"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
