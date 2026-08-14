"""Rhino host adapter for the Host Adapter Contract v1.

The HTTP server uses only the Python standard library so it runs inside
Rhino's bundled Python without extra dependencies. Document operations must run
on Rhino's main thread: they are queued and drained from ``RhinoApp.Idle`` (a
fallback daemon poller is used outside Rhino / in unit tests).
"""

from __future__ import annotations

import json
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional


SnapshotFn = Callable[[Dict[str, Any]], Dict[str, Any]]
ExecuteFn = Callable[[str, Dict[str, Any], bool], Dict[str, Any]]
RollbackFn = Callable[[str], Dict[str, Any]]


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler(adapter: "HostAdapter") -> type:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            if self.path.rstrip("/") == "/manifest":
                _json_response(self, 200, adapter.manifest())
                return
            if self.path.rstrip("/") == "/health":
                _json_response(self, 200, adapter.health())
                return
            _json_response(self, 404, {"ok": False, "error_code": "not_found", "error_message": "unknown endpoint"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            body = self._read_json()
            path = self.path.rstrip("/")
            if path == "/snapshot":
                _json_response(self, 200, adapter.snapshot((body or {}).get("scope") or {}))
                return
            if path == "/rollback":
                _json_response(self, 200, adapter.rollback((body or {}).get("rollback_token") or ""))
                return
            if path.startswith("/tools/"):
                tool_name = path[len("/tools/") :]
                _json_response(self, 200, adapter.execute_tool(tool_name, body or {}))
                return
            _json_response(self, 404, {"ok": False, "error_code": "not_found", "error_message": "unknown endpoint"})

        def _authorized(self) -> bool:
            supplied = self.headers.get("x-cadcopilot-token", "")
            if not adapter.token or supplied != adapter.token:
                _json_response(
                    self,
                    401,
                    {"ok": False, "error_code": "unauthorized", "error_message": "missing or invalid host token"},
                )
                return False
            return True

        def _read_json(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}

    return Handler


class HostAdapter:
    """Reference implementation of the host adapter contract (v1)."""

    def __init__(
        self,
        *,
        host_id: str,
        host_kind: str,
        product: str,
        product_version: str,
        tools: List[Dict[str, Any]],
        snapshot_fn: SnapshotFn,
        execute_fn: ExecuteFn,
        rollback_fn: Optional[RollbackFn] = None,
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
        self._tools = {tool["tool_name"]: dict(tool) for tool in tools}
        self._snapshot_fn = snapshot_fn
        self._execute_fn = execute_fn
        self._rollback_fn = rollback_fn
        self._httpd = HTTPServer((host, port), _make_handler(self))
        # Single-threaded server: Rhino's embedded CPython is thread-limited
        # (ThreadingHTTPServer's per-request threads triggered R6016 "not
        # enough space for thread data" after repeated startups). Requests are
        # local, small and infrequent; a serial serve loop is plenty.
        self.port = int(self._httpd.server_address[1])
        self.endpoint = f"http://{host}:{self.port}"
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

        return {
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
        }

    def manifest(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "host_id": self.host_id,
            "host_kind": self.host_kind,
            "product": self.product,
            "product_version": self.product_version,
            "protocol_version": self.protocol_version,
            "capabilities": ["snapshot", "dry_run", "rollback"],
            "tools": list(self._tools.values()),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "product": self.product,
            "product_version": self.product_version,
            "document_open": True,
            "detail": {"host_id": self.host_id, "endpoint": self.endpoint},
        }

    def snapshot(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        return self._snapshot_fn(scope)

    def execute_tool(self, tool_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"ok": False, "error_code": "unknown_tool", "error_message": f"unknown tool: {tool_name}"}
        arguments = dict(body.get("arguments") or {})
        dry_run = bool(body.get("dry_run", False))
        side_effect = str(tool.get("side_effect_level") or "none").strip().lower()
        if side_effect != "none" and not dry_run:
            permission_request_id = str(arguments.get("permission_request_id") or "").strip()
            if not permission_request_id:
                return {
                    "ok": False,
                    "error_code": "permission_required",
                    "error_message": "write tools require a permission_request_id when dry_run is false",
                }
        try:
            result = self._execute_fn(tool_name, arguments, dry_run)
        except Exception as exc:
            return {"ok": False, "error_code": "execution_error", "error_message": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "error_code": "bad_result", "error_message": "tool returned a non-object result"}
        result.setdefault("ok", True)
        result.setdefault("dry_run", dry_run)
        return result

    def rollback(self, rollback_token: str) -> Dict[str, Any]:
        if self._rollback_fn is None:
            return {"ok": False, "error_code": "rollback_unsupported", "error_message": "rollback is not supported"}
        if not rollback_token:
            return {"ok": False, "error_code": "invalid_arguments", "error_message": "rollback_token is required"}
        try:
            result = self._rollback_fn(rollback_token)
        except Exception as exc:
            return {"ok": False, "error_code": "execution_error", "error_message": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "error_code": "bad_result", "error_message": "rollback returned a non-object result"}
        result.setdefault("ok", True)
        return result


class RhinoExecutor:
    """Execute Rhino document operations on the main thread.

    ``execute()`` enqueues a job and waits for the result; the job is drained on
    Rhino's main thread from ``RhinoApp.Idle`` (installed once by ``install()``).
    Outside Rhino a daemon thread polls the queue so unit tests keep working.
    """

    def __init__(self, runner: Callable[[str, Dict[str, Any], bool], Dict[str, Any]]) -> None:
        self._runner = runner
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._installed = False
        self._processing = False
        self._fallback_thread: Optional[threading.Thread] = None
        self._timer = None
        self.timer_installed = False
        self._idle_installed = False

    def execute(self, tool_name: str, arguments: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        event = threading.Event()
        holder: Dict[str, Any] = {}
        self._queue.put((tool_name, arguments, dry_run, event, holder))
        self.install()
        # Wait for the main-thread drain.  If neither the WinForms timer nor
        # RhinoApp.Idle drains the queue (defensive fallback), execute directly
        # instead of hanging the caller forever.
        if event.wait(8):
            return holder.get("result", {"ok": False, "error_code": "no_result"})
        try:
            import os

            log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")
            with open(log_path, "a") as handle:
                handle.write("WATCHDOG: main-thread drain stalled; executing %s directly\n" % tool_name)
        except Exception:  # noqa: BLE001
            pass
        self._processing = True
        try:
            holder["result"] = self._runner(tool_name, arguments, dry_run)
        except Exception as exc:
            holder["result"] = {"ok": False, "error_code": "execution_error", "error_message": str(exc)}
        finally:
            event.set()
            self._processing = False
        return holder["result"]

    def poll(self) -> float:
        if self._processing:
            return 0.1
        self._processing = True
        try:
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                tool_name, arguments, dry_run, event, holder = item
                if event.is_set():
                    # Already handled by the watchdog fallback; skip.
                    continue
                try:
                    holder["result"] = self._runner(tool_name, arguments, dry_run)
                except Exception as exc:
                    holder["result"] = {"ok": False, "error_code": "execution_error", "error_message": str(exc)}
                finally:
                    event.set()
        finally:
            self._processing = False
        return 0.1

    def install(self) -> None:
        if self._installed:
            return
        try:
            import Rhino  # noqa: F401

            Rhino.RhinoApp.Idle += self._on_idle
            self._installed = True
            return
        except Exception:
            pass
        self.install_fallback()

    def install_main_thread_timer(self) -> None:
        """Create a WinForms timer on the calling (main) thread.

        Rhino's message pump processes WinForms timer ticks on the thread that
        created them; called from the startup script (main thread) this gives a
        reliable main-thread drain for document operations. ``RhinoApp.Idle``
        is hooked as a secondary drain for builds where it fires.
        """
        try:
            import System.Windows.Forms as _wf

            self._timer = _wf.Timer()
            self._timer.Interval = 100
            self._timer.Tick += lambda s, e: self.poll()
            self._timer.Start()
            self.timer_installed = True
            self._installed = True
        except Exception:
            self.install_fallback()
        # Secondary drain: RhinoApp.Idle fires whenever the app's message
        # queue goes empty.  If either channel works, queued document work is
        # drained on Rhino's main thread.
        try:
            import Rhino  # noqa: F401

            Rhino.RhinoApp.Idle += self._on_idle
            self._idle_installed = True
        except Exception:
            self._idle_installed = False

    def install_fallback(self) -> None:
        # Poll from a daemon thread (unit tests / non-Rhino runtimes).
        if self._fallback_thread is None:
            self._fallback_thread = threading.Thread(target=self._fallback_loop, daemon=True)
            self._fallback_thread.start()
            self._installed = True

    def _on_idle(self, sender: Any, e: Any) -> None:
        try:
            self.poll()
        except Exception:
            pass

    def _fallback_loop(self) -> None:
        while True:
            try:
                self.poll()
            except Exception:
                pass
            time.sleep(0.1)


__all__ = ["HostAdapter", "RhinoExecutor"]
