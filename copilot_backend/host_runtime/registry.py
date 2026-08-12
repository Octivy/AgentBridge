"""Host registration discovery.

Adapters write a small JSON file into ``%LOCALAPPDATA%/AgentBridge/hosts`` and
the client polls that directory. The file carries the endpoint and the random
token the adapter generated, so the client can authenticate with ``/health``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


REGISTRY_SCHEMA_VERSION = 1


def default_registry_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "AgentBridge" / "hosts"


@dataclass(frozen=True)
class HostRegistration:
    host_id: str
    host_kind: str
    product: str
    product_version: str
    protocol_version: str
    endpoint: str
    token: str
    pid: int
    registered_at: str
    schema_version: int = REGISTRY_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def write_registration(registry_dir: Path, registration: HostRegistration) -> Path:
    """Atomically persist a host registration file."""

    directory = Path(registry_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{registration.host_id}-{registration.pid}.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(
        json.dumps(registration.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, target)
    return target


def read_registration(path: Path) -> Optional[HostRegistration]:
    """Read and validate a single registration file."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return registration_from_dict(data)


def registration_from_dict(data: Mapping[str, Any]) -> Optional[HostRegistration]:
    try:
        if int(data.get("schema_version", 0)) != REGISTRY_SCHEMA_VERSION:
            return None
        return HostRegistration(
            host_id=str(data["host_id"]).strip(),
            host_kind=str(data["host_kind"]).strip(),
            product=str(data["product"]).strip(),
            product_version=str(data["product_version"]).strip(),
            protocol_version=str(data["protocol_version"]).strip(),
            endpoint=str(data["endpoint"]).strip(),
            token=str(data["token"]).strip(),
            pid=int(data["pid"]),
            registered_at=str(data["registered_at"]).strip(),
        )
    except (KeyError, TypeError, ValueError):
        return None


def list_registrations(registry_dir: Path) -> List[HostRegistration]:
    """Read all valid registration files in the directory."""

    directory = Path(registry_dir)
    if not directory.is_dir():
        return []
    registrations: List[HostRegistration] = []
    for path in directory.glob("*.json"):
        registration = read_registration(path)
        if registration is not None:
            registrations.append(registration)
    return registrations


def discover_hosts(registry_dir: Optional[Path] = None) -> List[HostRegistration]:
    """Discover hosts, preferring the most recent registration per host_id."""

    directory = registry_dir or default_registry_dir()
    by_host: Dict[str, HostRegistration] = {}
    for registration in list_registrations(directory):
        existing = by_host.get(registration.host_id)
        if existing is None or registration.registered_at > existing.registered_at:
            by_host[registration.host_id] = registration
    return sorted(by_host.values(), key=lambda item: item.host_id)


def remove_registration(registry_dir: Path, host_id: str, pid: Optional[int] = None) -> int:
    """Remove registration files for a host (optionally only for a given pid)."""

    directory = Path(registry_dir)
    removed = 0
    if not directory.is_dir():
        return removed
    for path in directory.glob("*.json"):
        registration = read_registration(path)
        if registration is None or registration.host_id != host_id:
            continue
        if pid is not None and registration.pid != pid:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "HostRegistration",
    "default_registry_dir",
    "discover_hosts",
    "list_registrations",
    "read_registration",
    "registration_from_dict",
    "remove_registration",
    "write_registration",
]
