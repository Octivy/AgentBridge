"""Headless Rhino host for the Host Adapter Contract v1.

Run inside Rhino's Python (EditPythonScript or startup script):

    import background_host
    background_host.main()

The package is self-contained: ``host.py`` / ``registration.py`` are bundled
copies, so it works from Rhino's scripts folder without the AgentBridge repo.

Compatible with Python 2.7 (Rhino 6 / IronPython) and Python 3 (Rhino 7+).
"""

from __future__ import absolute_import, division, print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import TOOLS, rollback, runner, snapshot  # noqa: E402
from host import HostAdapter, RhinoExecutor  # noqa: E402
from registration import write_registration  # noqa: E402


def _append_log(message):
    try:
        log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")
        with open(log_path, "a") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def _selftest(endpoint, token):
    """Probe our own /health over a raw socket and log the outcome.

    Uses a raw socket (not urllib2) so neither the system proxy nor the
    IronPython urllib2 proxy handling can produce a false negative.
    """
    try:
        import socket
        import time

        time.sleep(1.0)
        port = int(endpoint.rsplit(":", 1)[1])
        sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        req = (
            "GET /health HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "x-cadcopilot-token: %s\r\n"
            "Connection: close\r\n\r\n"
        ) % token
        try:
            # IronPython's sendall accepts str (the old "buffer" type); Python
            # 3 needs bytes.
            if isinstance(req, str) and not isinstance(req, bytes):
                sock.sendall(req.encode("utf-8"))
            else:
                sock.sendall(req)
        except Exception as exc:
            _append_log("SELFTEST sendall error: %r" % (exc,))
            try:
                sock.close()
            except Exception:
                pass
            return
        time.sleep(0.5)
        try:
            resp = sock.recv(4096)
        except Exception as exc:
            resp = "<recv error %r>" % (exc,)
        try:
            sock.close()
        except Exception:
            pass
        _append_log("SELFTEST response: %r" % (resp[:160],))
    except Exception as exc:
        _append_log("SELFTEST error: %r" % (exc,))


def main():
    # All Rhino document work must run on Rhino's main thread.  The executor
    # queues jobs and drains them from a WinForms timer / RhinoApp.Idle on the
    # thread that created it (the main thread when launched by the startup
    # script).  ``RhinoDoc.ActiveDoc`` is only reliable on the main thread, so
    # we never call the backend from the HTTP server thread directly.
    executor = RhinoExecutor(runner)
    executor.install_main_thread_timer()
    adapter = HostAdapter(
        host_id="rhino-main",
        host_kind="rhino",
        product="Rhino",
        product_version="1.0",
        tools=TOOLS,
        snapshot_fn=snapshot,
        execute_fn=executor.execute,
        rollback_fn=rollback,
    )
    adapter.start()
    write_registration(adapter.registration())
    print("AGENTBRIDGE_RHINO_HOST_READY %s %s" % (adapter.endpoint, adapter.token))
    try:
        sys.stdout.flush()
    except Exception:
        pass
    _selftest(adapter.endpoint, adapter.token)
    try:
        log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AgentBridge", "rhino-startup.log")
        with open(log_path, "a") as handle:
            handle.write(
                "host main() returned; timer=%s idle=%s\n"
                % (executor.timer_installed, executor._idle_installed)
            )
    except Exception:
        pass
    # Deliberately no blocking loop: the HTTP server runs on a daemon thread
    # and the WinForms timer / Idle hook drains document work on the main
    # thread, so the startup script returns and Rhino stays responsive.


if __name__ == "__main__":
    main()
