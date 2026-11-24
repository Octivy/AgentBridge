"""Client-side host discovery and invocation for the Host Adapter Contract v1."""

from host_runtime.client import HostClient, HostError
from host_runtime.manifest import validate_manifest
from host_runtime.registry import (
    HostRegistration,
    discover_hosts,
    list_registrations,
    read_registration,
    remove_registration,
    write_registration,
)

__all__ = [
    "HostClient",
    "HostError",
    "HostRegistration",
    "discover_hosts",
    "list_registrations",
    "read_registration",
    "remove_registration",
    "validate_manifest",
    "write_registration",
]
