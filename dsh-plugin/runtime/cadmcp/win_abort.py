"""Suppress CRT error dialogs for MCP stdio servers on Windows.

R6016 ("not enough space for thread data") and other runtime errors abort the
C runtime, which by default shows a modal "Microsoft Visual C++ Runtime
Library" dialog. For an MCP stdio server that dialog is pure harm: it freezes
the subprocess as a zombie (the dialog thread survives process exit) and
confuses users. These servers are subprocesses — when the CRT aborts they must
die silently so the client sees the pipe close and reports a clean error.

Two independent CRT mechanisms are silenced:

- ``_set_error_mode(_OUT_TO_STDERR)``: controls the R6016-class *runtime
  error* dialog (the "Microsoft Visual C++ Runtime Library" box). Writing to
  stderr instead of a dialog is exactly right for subprocesses.
- ``_set_abort_behavior(0, _WRITE_ABORT_MSG)``: controls the plain ``abort()``
  message box.

WER reporting (ReportFault) is deliberately left enabled, so LocalDumps still
captures a dump for offline diagnosis.
"""

import os

_WRITE_ABORT_MSG = 0x1
_OUT_TO_STDERR = 1  # _CRT_ERROR mode: print runtime errors to stderr, no dialog


def silence_abort_dialogs() -> None:
    """Disable the CRT runtime-error/abort message boxes for this process."""

    if os.name != "nt":
        return
    try:
        import ctypes

        ucrt = ctypes.CDLL("ucrtbase")
        # R6016 box lives on the _CRT_ERROR path -> stderr instead of a dialog.
        ucrt._set_error_mode(_OUT_TO_STDERR)
        # Plain abort(): keep WER, drop the message box.
        ucrt._set_abort_behavior(0, _WRITE_ABORT_MSG)
    except Exception:  # noqa: BLE001 - best-effort hardening, never fatal
        pass
