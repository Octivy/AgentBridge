"""Consumable deliverables: open, reveal, preview and rollback actions.

The delivery list used to stop at "registered" — cards showed name/type/path
but offered nothing to do with them. These actions close that gap:

- open/reveal the file with the OS shell;
- serve the file for inline preview (screenshots, reports);
- parse tool-token ledgers (both shapes the Rhino pipeline produced) and roll
  individual tokens back through whichever registered host supports rollback.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from delivery.models import Deliverable
from delivery.service import DeliveryService, delivery_service
from host_runtime.client import HostClient, HostError
from host_runtime.registry import default_registry_dir, discover_hosts

PREVIEW_MAX_BYTES = 30 * 1024 * 1024


class DeliverableNotFound(KeyError):
    """Task or deliverable index does not exist."""


class DeliverableActionError(ValueError):
    """The action cannot be performed (missing file, no host online, ...)."""


def get_deliverable(
    task_id: str, index: int, service: Optional[DeliveryService] = None
) -> Deliverable:
    view = (service or delivery_service).get(task_id)
    if view is None:
        raise DeliverableNotFound(task_id)
    if index < 0 or index >= len(view.deliverables):
        raise DeliverableNotFound(f"{task_id}#{index}")
    return view.deliverables[index]


def _existing_path(deliverable: Deliverable) -> Path:
    path = Path(deliverable.path).expanduser()
    if not path.exists():
        raise DeliverableActionError(f"文件不存在：{path}")
    return path


def open_deliverable(task_id: str, index: int, service: Optional[DeliveryService] = None) -> Dict[str, Any]:
    deliverable = get_deliverable(task_id, index, service)
    path = _existing_path(deliverable)
    if hasattr(os, "startfile"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return {"ok": True, "path": str(path)}


def reveal_deliverable(task_id: str, index: int, service: Optional[DeliveryService] = None) -> Dict[str, Any]:
    deliverable = get_deliverable(task_id, index, service)
    path = _existing_path(deliverable)
    if os.name == "nt":
        subprocess.Popen(["explorer", f"/select,{path}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
    return {"ok": True, "path": str(path)}


def preview_info(task_id: str, index: int, service: Optional[DeliveryService] = None) -> Dict[str, Any]:
    deliverable = get_deliverable(task_id, index, service)
    path = _existing_path(deliverable)
    if not path.is_file():
        raise DeliverableActionError("该交付物不是可预览的文件")
    size = path.stat().st_size
    if size > PREVIEW_MAX_BYTES:
        raise DeliverableActionError(f"文件过大（{size} 字节），不提供在线预览")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {"path": str(path), "size": size, "content_type": content_type, "name": deliverable.name}


def read_rollback_tokens(path: Path) -> List[Dict[str, str]]:
    """Parse rollback tokens from a tool-token ledger.

    Known shapes:
    - ``{"created": [[name, rollback_token], ...]}`` (house-build.json)
    - ``{"objects": [{name, rollback_token, ...}, ...]}`` (plan-build.json)
    - ``{"tokens"|"rollback_tokens": [{name, token}, ...]}`` (generic)
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeliverableActionError(f"台账读取失败：{exc}") from exc

    found: List[Dict[str, str]] = []
    if isinstance(data, dict):
        for pair in data.get("created") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2 and pair[1]:
                found.append({"name": str(pair[0]), "token": str(pair[1])})
        for item in data.get("objects") or []:
            if isinstance(item, dict) and item.get("rollback_token"):
                found.append({"name": str(item.get("name") or ""), "token": str(item["rollback_token"])})
        for key in ("tokens", "rollback_tokens"):
            for item in data.get(key) or []:
                if isinstance(item, dict) and item.get("token"):
                    found.append({"name": str(item.get("name") or ""), "token": str(item["token"])})

    seen = set()
    tokens: List[Dict[str, str]] = []
    for entry in found:
        if entry["token"] in seen:
            continue
        seen.add(entry["token"])
        tokens.append(entry)
    return tokens


def ledger_deliverable_tokens(
    task_id: str, index: int, service: Optional[DeliveryService] = None
) -> List[Dict[str, str]]:
    deliverable = get_deliverable(task_id, index, service)
    path = _existing_path(deliverable)
    if not path.is_file():
        raise DeliverableActionError("该交付物不是台账文件")
    return read_rollback_tokens(path)


def rollback_deliverable(
    task_id: str,
    index: int,
    token: str,
    *,
    service: Optional[DeliveryService] = None,
    registry_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Roll one token back through the first registered host that accepts it."""

    token = (token or "").strip()
    if not token:
        raise DeliverableActionError("rollback_token 是必填项")

    tokens = ledger_deliverable_tokens(task_id, index, service)
    if tokens and token not in {entry["token"] for entry in tokens}:
        raise DeliverableActionError("回滚令牌不属于该交付物台账")

    registrations = discover_hosts(Path(registry_dir or default_registry_dir()))
    attempted: List[Dict[str, str]] = []
    for registration in registrations:
        try:
            client = HostClient(registration.endpoint, registration.token, timeout_seconds=10)
            result = client.rollback(token)
            return {"ok": True, "host_id": registration.host_id, "token": token, "result": result}
        except HostError as exc:
            attempted.append(
                {"host_id": registration.host_id, "error": str(exc), "error_code": exc.error_code}
            )

    if not attempted:
        raise DeliverableActionError("当前没有已注册的在线宿主，请先在软件配置页连接软件再回滚。")
    raise DeliverableActionError(
        "没有在线宿主能执行该回滚：" + json.dumps(attempted, ensure_ascii=False)
    )


__all__ = [
    "DeliverableActionError",
    "DeliverableNotFound",
    "get_deliverable",
    "ledger_deliverable_tokens",
    "open_deliverable",
    "preview_info",
    "read_rollback_tokens",
    "reveal_deliverable",
    "rollback_deliverable",
]
