"""Pydantic models for the host adapter configuration center."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class LaunchSpec(BaseModel):
    """How to launch this software's bridge process (stdin/stdout MCP server)."""

    command: str = ""
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    env_vars: List[str] = Field(default_factory=list, description="Environment variable names to pass through")
    cwd: str = ""
    transport: str = "stdio"


class HostAdapterConfig(BaseModel):
    """A configured software bridge (AutoCAD, Blender, SketchUp, Rhino, ...)."""

    host_id: str
    name: str
    host_kind: str
    product: str = ""
    enabled: bool = True
    auto_start: bool = False
    launch: LaunchSpec = Field(default_factory=LaunchSpec)
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


class HostConfigCreate(BaseModel):
    host_id: str
    name: str
    host_kind: str
    product: str = ""
    enabled: bool = True
    auto_start: bool = False
    launch: LaunchSpec = Field(default_factory=LaunchSpec)
    notes: str = ""


class HostConfigUpdate(BaseModel):
    name: Optional[str] = None
    host_kind: Optional[str] = None
    product: Optional[str] = None
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    launch: Optional[LaunchSpec] = None
    notes: Optional[str] = None


class HostConfigStatus(BaseModel):
    """Live status of a configured software bridge."""

    host_id: str
    name: str
    host_kind: str
    product: str
    enabled: bool
    auto_start: bool
    configured: bool
    process_running: bool
    pid: Optional[int] = None
    registered: bool
    registered_host_id: str = ""
    product_version: str = ""
    endpoint: str = ""
    health_ok: bool = False
    error: str = ""


class HostTestResult(BaseModel):
    host_id: str
    ok: bool
    product: str = ""
    product_version: str = ""
    endpoint: str = ""
    message: str = ""
