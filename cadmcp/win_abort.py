"""Suppress CRT abort dialogs for MCP stdio servers on Windows.

R6016 ("not enough space for thread data") aborts the C runtime, which by
default shows a modal "Microsoft Visual C++ Runtime Library" dialog. For an
MCP stdio server that dialog is pure harm: it freezes the subprocess as a
zombie (the dialog thread survives process exit) and confuses users. These
servers are subprocesses — when the CRT aborts they must die silently so the
client sees the pipe close and reports a clean error.

WER reporting (ReportFault) is deliberately left enabled, so LocalDumps still
captures a dump for offline diagnosis.
"""

import os

_WRITE_ABORT_MSG = 0x1


def silence_abort_dialogs() -> None:
    """Disable the CRT abort message box for this process (best-effort)."""

    if os.name != "nt":
        return
    try:
        import ctypes

        # _set_abort_behavior(flags=0, mask=_WRITE_ABORT_MSG): keep WER, drop the dialog.
        ctypes.CDLL("ucrtbase")._set_abort_behavior(0, _WRITE_ABORT_MSG)
    except Exception:  # noqa: BLE001 - best-effort hardening, never fatal
        pass
