"""Standalone registration helper for host adapters.

Adapters live inside target applications (Blender, SketchUp, Rhino...) and must
not depend on the AgentBridge backend, so this module intentionally has no
project imports. It writes the same registration JSON that the client-side
``host_runtime.registry`` reads.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


REGISTRY_SCHEMA_VERSION = 1


def default_registry_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "hosts"


def build_registration(
    *,
    host_id: str,
    host_kind: str,
    product: str,
    product_version: str,
    protocol_version: str,
    endpoint: str,
    token: str,
    pid: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "host_id": host_id,
        "host_kind": host_kind,
        "product": product,
        "product_version": product_version,
        "protocol_version": protocol_version,
        "endpoint": endpoint,
        "token": token,
        "pid": pid if pid is not None else os.getpid(),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


def write_registration(registration: Dict[str, Any], registry_dir: Optional[Path] = None) -> Path:
    directory = registry_dir or default_registry_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{registration['host_id']}-{registration['pid']}.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(
        json.dumps(registration, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, target)
    return target


def remove_registration(
    host_id: str,
    pid: Optional[int] = None,
    registry_dir: Optional[Path] = None,
) -> int:
    directory = registry_dir or default_registry_dir()
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


__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "build_registration",
    "default_registry_dir",
    "remove_registration",
    "write_registration",
]
