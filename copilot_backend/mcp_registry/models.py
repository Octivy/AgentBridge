"""Models for MCP server registration and generated agent configs."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class McpServerEntry(BaseModel):
    name: str
    command: str
    args: List[str] = Field(default_factory=list)
    cwd: str = ""
    env_vars: List[str] = Field(default_factory=list)
    approval_mode: str = "approve"
    enabled: bool = True
    required: bool = False
    startup_timeout_sec: int = 20
    tool_timeout_sec: int = 60


class McpPreviewResponse(BaseModel):
    servers: List[McpServerEntry]
    codex_toml: str
    claude_json: Dict[str, object]


class McpWriteRequest(BaseModel):
    target_path: Optional[str] = None


class McpWriteResult(BaseModel):
    path: str
    servers: List[str]


class McpStatusResponse(BaseModel):
    codex_path: str
    codex_servers: List[str]
    generated_servers: List[str]
