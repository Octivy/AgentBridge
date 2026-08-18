"""Standalone registration helper for host adapters.

Adapters live inside target applications (Blender, SketchUp, Rhino...) and must
not depend on the AgentBridge backend, so this module intentionally has no
project imports. It writes the same registration JSON that the client-side
``host_runtime.registry`` reads.

This module is compatible with both Python 2.7 (Rhino 6 / IronPython) and
Python 3 (Rhino 7+ / CPython): no annotations, no f-strings, no pathlib, and
conditional use of ``os.replace`` / ``datetime.timezone``.
"""

from __future__ import absolute_import, division, print_function

import datetime
import io
import json
import os


REGISTRY_SCHEMA_VERSION = 1

try:
    _UTC = datetime.timezone.utc

    def _utc_now_iso():
        return datetime.datetime.now(_UTC).isoformat()

except AttributeError:  # Python 2.7 has no datetime.timezone

    def _utc_now_iso():
        return datetime.datetime.utcnow().isoformat() + "Z"


def default_registry_dir():
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "AgentBridge", "hosts")


def build_registration(
    host_id,
    host_kind,
    product,
    product_version,
    protocol_version,
    endpoint,
    token,
    pid=None,
):
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
        "registered_at": _utc_now_iso(),
    }


def _atomic_replace(temp, target):
    try:
        os.replace(temp, target)  # Python 3.3+
    except AttributeError:  # Python 2.7
        try:
            os.remove(target)
        except OSError:
            pass
        os.rename(temp, target)


def write_registration(registration, registry_dir=None):
    directory = registry_dir or default_registry_dir()
    if not os.path.isdir(directory):
        os.makedirs(directory)
    target = os.path.join(directory, "%s-%s.json" % (registration["host_id"], registration["pid"]))
    temp = target + ".tmp"
    payload = json.dumps(registration, ensure_ascii=False, indent=2, sort_keys=True)
    with io.open(temp, "w", encoding="utf-8") as handle:
        handle.write(payload)
    _atomic_replace(temp, target)
    return target


def remove_registration(host_id, pid=None, registry_dir=None):
    directory = registry_dir or default_registry_dir()
    removed = 0
    if not os.path.isdir(directory):
        return removed
    for name in os.listdir(directory):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            with io.open(path, "r", encoding="utf-8") as handle:
                data = json.loads(handle.read())
        except (OSError, ValueError):
            continue
        if data.get("host_id") != host_id:
            continue
        if pid is not None and int(data.get("pid") or -1) != pid:
            continue
        try:
            os.remove(path)
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
