"""Generate a Host Adapter skeleton for software without MCP support."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


REGISTRATION_PY = '''"""Self-contained host registration helper (Host Adapter Contract v1)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def default_registry_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "hosts"


def write_registration(registration: Dict[str, Any]) -> Path:
    directory = default_registry_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{registration['host_id']}-{registration['pid']}.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(
        json.dumps(registration, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, target)
    return target


def remove_registration(host_id: str, pid: Optional[int] = None) -> int:
    directory = default_registry_dir()
    removed = 0
    if not directory.is_dir():
        return removed
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("host_id") != host_id:
            continue
        if pid is not None and int(data.get("pid") or -1) != pid:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


__all__ = ["default_registry_dir", "remove_registration", "write_registration"]
'''


HOST_PY = '''"""{product} host adapter (Host Adapter Contract v1) - stdlib only."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler(adapter: "HostAdapter") -> type:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            if not self._authorized():
                return
            path = self.path.rstrip("/")
            if path == "/manifest":
                _json_response(self, 200, adapter.manifest())
            elif path == "/health":
                _json_response(self, 200, adapter.health())
            else:
                _json_response(self, 404, {{"ok": False, "error_code": "not_found", "error_message": "unknown endpoint"}})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            body = self._read_json()
            path = self.path.rstrip("/")
            if path == "/snapshot":
                _json_response(self, 200, adapter.snapshot((body or {{}}).get("scope") or {{}}))
            elif path == "/rollback":
                _json_response(self, 200, adapter.rollback((body or {{}}).get("rollback_token") or ""))
            elif path.startswith("/tools/"):
                tool_name = path[len("/tools/"):]
                _json_response(self, 200, adapter.execute_tool(tool_name, body or {{}}))
            else:
                _json_response(self, 404, {{"ok": False, "error_code": "not_found", "error_message": "unknown endpoint"}})

        def _authorized(self) -> bool:
            supplied = self.headers.get("x-cadcopilot-token", "")
            if not adapter.token or supplied != adapter.token:
                _json_response(self, 401, {{"ok": False, "error_code": "unauthorized", "error_message": "missing or invalid host token"}})
                return False
            return True

        def _read_json(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                return {{}}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {{}}

    return Handler


class HostAdapter:
    """Reference host adapter implementation (contract v1)."""

    def __init__(
        self,
        *,
        host_id: str,
        host_kind: str,
        product: str,
        product_version: str,
        tools: List[Dict[str, Any]],
        snapshot_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        execute_fn: Callable[[str, Dict[str, Any], bool], Dict[str, Any]],
        rollback_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        token: Optional[str] = None,
        host: str = "127.0.0.1",
        port: int = 0,
        protocol_version: str = "1.0",
    ) -> None:
        self.host_id = host_id
        self.host_kind = host_kind
        self.product = product
        self.product_version = product_version
        self.protocol_version = protocol_version
        self.token = token or secrets.token_hex(32)
        self._tools = {{tool["tool_name"]: dict(tool) for tool in tools}}
        self._snapshot_fn = snapshot_fn
        self._execute_fn = execute_fn
        self._rollback_fn = rollback_fn
        self._httpd = ThreadingHTTPServer((host, port), _make_handler(self))
        self.port = int(self._httpd.server_address[1])
        self.endpoint = f"http://{{host}}:{{self.port}}"
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def registration(self) -> Dict[str, Any]:
        import os
        from datetime import datetime, timezone

        return {{
            "schema_version": 1,
            "host_id": self.host_id,
            "host_kind": self.host_kind,
            "product": self.product,
            "product_version": self.product_version,
            "protocol_version": self.protocol_version,
            "endpoint": self.endpoint,
            "token": self.token,
            "pid": os.getpid(),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }}

    def manifest(self) -> Dict[str, Any]:
        return {{
            "schema_version": 1,
            "host_id": self.host_id,
            "host_kind": self.host_kind,
            "product": self.product,
            "product_version": self.product_version,
            "protocol_version": self.protocol_version,
            "capabilities": ["snapshot", "dry_run", "rollback"],
            "tools": list(self._tools.values()),
        }}

    def health(self) -> Dict[str, Any]:
        return {{
            "ok": True,
            "product": self.product,
            "product_version": self.product_version,
            "document_open": True,
            "detail": {{"host_id": self.host_id, "endpoint": self.endpoint}},
        }}

    def snapshot(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        return self._snapshot_fn(scope)

    def execute_tool(self, tool_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._tools.get(tool_name)
        if tool is None:
            return {{"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {{tool_name}}"}}
        arguments = dict(body.get("arguments") or {{}})
        dry_run = bool(body.get("dry_run", False))
        side_effect = str(tool.get("side_effect_level") or "none").strip().lower()
        if side_effect != "none" and not dry_run:
            permission_request_id = str(arguments.get("permission_request_id") or "").strip()
            if not permission_request_id:
                return {{
                    "ok": False,
                    "error_code": "permission_required",
                    "error_message": "write tools require a permission_request_id when dry_run is false",
                }}
        try:
            result = self._execute_fn(tool_name, arguments, dry_run)
        except Exception as exc:
            return {{"ok": False, "error_code": "execution_error", "error_message": str(exc)}}
        if not isinstance(result, dict):
            return {{"ok": False, "error_code": "bad_result", "error_message": "tool returned a non-object result"}}
        result.setdefault("ok", True)
        result.setdefault("dry_run", dry_run)
        return result

    def rollback(self, rollback_token: str) -> Dict[str, Any]:
        if self._rollback_fn is None:
            return {{"ok": False, "error_code": "rollback_unsupported", "error_message": "rollback is not supported"}}
        if not rollback_token:
            return {{"ok": False, "error_code": "invalid_arguments", "error_message": "rollback_token is required"}}
        try:
            result = self._rollback_fn(rollback_token)
        except Exception as exc:
            return {{"ok": False, "error_code": "execution_error", "error_message": str(exc)}}
        result.setdefault("ok", True)
        return result


__all__ = ["HostAdapter"]
'''


BACKEND_PY = '''"""{{product}} backend: tools and operations (stdlib only)."""

from __future__ import annotations

from typing import Any, Dict


TOOLS = [
    {{
        "tool_name": "{kind}_summary",
        "display_name": "{product} 场景摘要",
        "category": "analysis",
        "description": "汇总当前 {product} 的状态与对象。",
        "input_schema": {{"type": "object", "properties": {{}}, "additionalProperties": False}},
        "dry_run_supported": False,
        "side_effect_level": "none",
        "result_schema": {{"type": "object"}},
    }},
    {{
        "tool_name": "{kind}_create_thing",
        "display_name": "创建示例对象",
        "category": "modeling",
        "description": "预览并创建一个示例对象（可回滚）。请按目标软件的真实 API 补全实现。",
        "input_schema": {{
            "type": "object",
            "properties": {{
                "name": {{"type": "string"}},
                "size": {{"type": "number", "exclusiveMinimum": 0}},
            }},
            "additionalProperties": False,
        }},
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {{"type": "object"}},
        "rollback_supported": True,
    }},
]


def summary() -> Dict[str, Any]:
    """TODO: 对接 {product} 的真实 API，返回当前文档/场景状态。"""
    return {{
        "schema_version": 1,
        "source": "{kind}",
        "state": "ok",
        "object_count": 0,
        "objects": [],
    }}


def snapshot(scope: Dict[str, Any]) -> Dict[str, Any]:
    del scope
    return {{"ok": True, "snapshot": summary()}}


def runner(tool_name: str, arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if tool_name == "{kind}_summary":
        return {{"ok": True, "result": summary(), "dry_run": False}}
    if tool_name == "{kind}_create_thing":
        return create_thing(arguments, dry_run)
    return {{"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {{tool_name}}"}}


def create_thing(arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    name = str(arguments.get("name") or "{Kind}Thing")
    size = float(arguments.get("size") or 2.0)
    preview = {{"object_name": name, "size": size}}
    if dry_run:
        return {{"ok": True, "result": {{"preview": preview}}, "dry_run": True}}
    # TODO: 在此调用 {product} 的真实创建 API，成功后返回 rollback_token。
    return {{
        "ok": True,
        "result": {{"object_name": name, "size": size}},
        "dry_run": False,
        "rollback_token": f"{{kind}}-thing-{{name}}",
    }}


def rollback(rollback_token: str) -> Dict[str, Any]:
    # TODO: 按 rollback_token 删除真实对象。
    return {{"ok": True, "result": {{"rolled_back": True, "rollback_token": rollback_token}}}}


__all__ = ["TOOLS", "create_thing", "rollback", "runner", "snapshot", "summary"]
'''


BACKGROUND_HOST_PY = '''"""Headless {product} host for the Host Adapter Contract v1."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import TOOLS, rollback, runner, snapshot  # noqa: E402
from host import HostAdapter  # noqa: E402
from registration import write_registration  # noqa: E402


def main() -> None:
    adapter = HostAdapter(
        host_id="{kind}-main",
        host_kind="{kind}",
        product="{product}",
        product_version="1.0",
        tools=TOOLS,
        snapshot_fn=snapshot,
        execute_fn=runner,
        rollback_fn=rollback,
    )
    adapter.start()
    write_registration(adapter.registration())
    print(f"AGENTBRIDGE_{kind_upper}_HOST_READY {{adapter.endpoint}} {{adapter.token}}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        adapter.stop()


if __name__ == "__main__":
    main()
'''


README_MD = """# {product} Host Adapter（脚手架）

这是为 **{product}** 生成的 Host Adapter 脚手架（Host Adapter Contract v1）。

## 已生成文件

- `host.py` — 标准库 HTTP 宿主（/manifest、/health、/snapshot、/rollback、/tools/<name>）
- `backend.py` — 工具定义与业务操作（`{kind}_summary` 读取、`{kind}_create_thing` 写预览/事务）
- `registration.py` — 向 `%LOCALAPPDATA%\\AgentBridge\\hosts` 写入注册
- `background_host.py` — 无界面启动入口，启动后打印 `AGENTBRIDGE_{kind}_HOST_READY`

## 下一步（由 Agent 或人工补全）

1. 在 `backend.py` 中对接 {product} 的真实 API（读取文档/场景、执行操作、返回 rollback_token）。
2. 把该目录放进 {product} 的插件/扩展（或通过命令行 `python background_host.py` 运行）。
3. 启动后在 AgentBridge 配置中心“连接监控”中应能看到 `{kind}` 在线。
4. 在配置中心为它配置启动命令，或直接通过控制面 MCP 的 `ab_add_host` 注册。

## 契约要点

- 写工具必须先 `dry_run=true` 预览，客户端签发一次性 permission ticket 后才能提交。
- 提交必须携带 `permission_request_id`；支持回滚的工具返回 `rollback_token`。
"""


def scaffold_adapter(
    host_kind: str,
    product: str,
    target_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate a working Host Adapter skeleton into ``adapters/<host_kind>``."""

    kind = str(host_kind or "").strip().lower().replace(" ", "_")
    if not kind:
        raise ValueError("host_kind is required")
    if not product or not product.strip():
        raise ValueError("product is required")
    product = product.strip()
    kind_title = kind.replace("_", " ").title().replace(" ", "")
    target = Path(target_dir) if target_dir else Path(__file__).resolve().parents[2] / "adapters" / kind
    target.mkdir(parents=True, exist_ok=True)

    files = {
        "host.py": HOST_PY.format(product=product),
        "backend.py": BACKEND_PY.format(kind=kind, product=product, Kind=kind_title),
        "registration.py": REGISTRATION_PY,
        "background_host.py": BACKGROUND_HOST_PY.format(kind=kind, kind_upper=kind.upper(), product=product),
        "README.md": README_MD.format(kind=kind, product=product),
    }
    for name, content in files.items():
        path = target / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    return {
        "target_dir": str(target),
        "files": sorted(files),
        "instruction": f"补全 backend.py 中 {product} 的真实 API，然后运行 python background_host.py",
    }


__all__ = ["scaffold_adapter"]
