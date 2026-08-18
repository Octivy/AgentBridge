"""Rhino host adapter for the Host Adapter Contract v1.

The HTTP server uses only the Python standard library so it runs inside
Rhino's bundled Python without extra dependencies. Document operations must run
on Rhino's main thread: they are queued and drained from ``RhinoApp.Idle`` (a
fallback daemon poller is used outside Rhino / in unit tests).

Compatible with Python 2.7 (Rhino 6 / IronPython) and Python 3 (Rhino 7+).
"""

from __future__ import absolute_import, division, print_function

import json
import os
import threading
import time

try:
    import queue  # Python 3
except ImportError:
    import Queue as queue  # Python 2.7

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer  # Python 3
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer  # Python 2.7


def _new_token():
    try:
        import secrets  # Python 3.6+
        return secrets.token_hex(32)
    except ImportError:
        pass
    try:
        import binascii
        return binascii.hexlify(os.urandom(32)).decode("ascii")
    except Exception:
        pass
    # Last-resort fallback for runtimes without os.urandom (some IronPython builds).
    import random
    random.seed()
    return "".join("%08x" % random.getrandbits(32) for _ in range(8))


def _json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        byte_len = len(body.encode("utf-8"))
    except (UnicodeDecodeError, AttributeError):
        byte_len = len(body)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(byte_len))
    handler.end_headers()
    handler._send(body)


def _make_handler(adapter):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send(self, data):
            # IronPython 2.7's socket.sendall accepts str (the old "buffer"
            # type) but rejects bytearray; Python 3 needs bytes. Route around
            # wfile entirely to avoid IronPython's broken SocketFile which
            # does memoryview(str) and fails with "expected IBufferProtocol".
            if isinstance(data, str) and not isinstance(data, bytes):
                data = data.encode("utf-8")
            self.connection.sendall(data)

        def send_response(self, code, message=None):
            self.log_request(code)
            if message is None:
                if code in self.responses:
                    message = self.responses[code][0]
                else:
                    message = ''
            self._send("HTTP/1.0 %d %s\r\n" % (code, message))

        def send_header(self, keyword, value):
            self._send("%s: %s\r\n" % (keyword, value))

        def end_headers(self):
            self._send("\r\n")

        def finish(self):
            try:
                self.connection.close()
            except Exception:
                pass

        def do_GET(self):
            if not self._authorized():
                return
            if self.path.rstrip("/") == "/manifest":
                _json_response(self, 200, adapter.manifest())
                return
            if self.path.rstrip("/") == "/health":
                _json_response(self, 200, adapter.health())
                return
            _json_response(self, 404, {"ok": False, "error_code": "not_found", "error_message": "unknown endpoint"})

        def do_POST(self):
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
                tool_name = path[len("/tools/"):]
                _json_response(self, 200, adapter.execute_tool(tool_name, body or {}))
                return
            _json_response(self, 404, {"ok": False, "error_code": "not_found", "error_message": "unknown endpoint"})

        def _authorized(self):
            supplied = self.headers.get("x-cadcopilot-token", "")
            if not adapter.token or supplied != adapter.token:
                _json_response(
                    self,
                    401,
                    {"ok": False, "error_code": "unauthorized", "error_message": "missing or invalid host token"},
                )
                return False
            return True

        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                return json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return {}

    return Handler


class HostAdapter:
    """Reference implementation of the host adapter contract (v1)."""

    def __init__(
        self,
        host_id,
        host_kind,
        product,
        product_version,
        tools,
        snapshot_fn,
        execute_fn,
        rollback_fn=None,
        token=None,
        host="127.0.0.1",
        port=0,
        protocol_version="1.0",
    ):
        self.host_id = host_id
        self.host_kind = host_kind
        self.product = product
        self.product_version = product_version
        self.protocol_version = protocol_version
        self.token = token or _new_token()
        self._tools = dict((tool["tool_name"], dict(tool)) for tool in tools)
        self._snapshot_fn = snapshot_fn
        self._execute_fn = execute_fn
        self._rollback_fn = rollback_fn
        self._httpd = HTTPServer((host, port), _make_handler(self))
        # Single-threaded server: embedded Python is thread-limited and
        # per-request threads can exhaust thread data after repeated startups.
        # Requests are local, small and infrequent; a serial serve loop is plenty.
        self.port = int(self._httpd.server_address[1])
        self.endpoint = "http://%s:%s" % (host, self.port)
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    def registration(self):
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
            "registered_at": _utc_now_iso(),
        }

    def manifest(self):
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

    def health(self):
        return {
            "ok": True,
            "product": self.product,
            "product_version": self.product_version,
            "document_open": True,
            "detail": {"host_id": self.host_id, "endpoint": self.endpoint},
        }

    def snapshot(self, scope):
        return self._snapshot_fn(scope)

    def execute_tool(self, tool_name, body):
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"ok": False, "error_code": "unknown_tool", "error_message": "unknown tool: %s" % tool_name}
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

    def rollback(self, rollback_token):
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

    def __init__(self, runner):
        self._runner = runner
        self._queue = queue.Queue()
        self._installed = False
        self._processing = False
        self._fallback_thread = None
        self._timer = None
        self.timer_installed = False
        self._idle_installed = False

    def execute(self, tool_name, arguments, dry_run):
        event = threading.Event()
        holder = {}
        self._queue.put((tool_name, arguments, dry_run, event, holder))
        self.install()
        # Wait for the main-thread drain.  If neither the WinForms timer nor
        # RhinoApp.Idle drains the queue (defensive fallback), execute directly
        # instead of hanging the caller forever.
        if event.wait(8):
            return holder.get("result", {"ok": False, "error_code": "no_result"})
        try:
            log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")
            with open(log_path, "a") as handle:
                handle.write("WATCHDOG: main-thread drain stalled; executing %s directly\n" % tool_name)
        except Exception:
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

    def poll(self):
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

    def install(self):
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

    def install_main_thread_timer(self):
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

    def install_fallback(self):
        # Poll from a daemon thread (unit tests / non-Rhino runtimes).
        if self._fallback_thread is None:
            self._fallback_thread = threading.Thread(target=self._fallback_loop)
            self._fallback_thread.daemon = True
            self._fallback_thread.start()
            self._installed = True

    def _on_idle(self, sender, e):
        try:
            self.poll()
        except Exception:
            pass

    def _fallback_loop(self):
        while True:
            try:
                self.poll()
            except Exception:
                pass
            time.sleep(0.1)


def _utc_now_iso():
    import datetime

    try:
        utc = datetime.timezone.utc
        return datetime.datetime.now(utc).isoformat()
    except AttributeError:  # Python 2.7
        return datetime.datetime.utcnow().isoformat() + "Z"


__all__ = ["HostAdapter", "RhinoExecutor"]
