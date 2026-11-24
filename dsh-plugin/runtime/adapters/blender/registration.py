"""Self-contained host registration helper bundled with the Blender add-on.

Blender add-ons must not depend on the AgentBridge repository layout, so this
module is a copy of ``adapters/_shared/registration.py`` kept inside the add-on
package. It writes the same registration JSON the client reads.
"""

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
