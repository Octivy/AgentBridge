from dataclasses import dataclass, field
from typing import Any

from harness.tools import HarnessRiskLevel


@dataclass
class HarnessToolResult:
    tool_name: str
    summary: str
    ok: bool = True
    assistant_message: str = ""
    data: Any = None
    dry_run: bool | None = None
    risk_level: HarnessRiskLevel | str = HarnessRiskLevel.READ_ONLY
    requires_permission: bool = False
    permission_request_id: str | None = None
    affected_entities_count: int | None = None
    affected_entities: list[dict[str, Any]] = field(default_factory=list)
    cad_operations: list[dict[str, Any]] = field(default_factory=list)
    preview: dict[str, Any] = field(default_factory=dict)
    transaction: dict[str, Any] = field(default_factory=dict)
    next_action: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        risk_level = self.risk_level.value if hasattr(self.risk_level, "value") else str(self.risk_level)
        return {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "summary": self.summary,
            "assistant_message": self.assistant_message,
            "data": self.data,
            "dry_run": self.dry_run,
            "risk_level": risk_level,
            "requires_permission": self.requires_permission,
            "permission_request_id": self.permission_request_id,
            "affected_entities_count": self.affected_entities_count,
            "affected_entities": list(self.affected_entities),
            "cad_operations": list(self.cad_operations),
            "preview": dict(self.preview),
            "transaction": dict(self.transaction),
            "next_action": dict(self.next_action),
            "audit": dict(self.audit),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "request_id": self.request_id,
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        return {
            "ok": payload["ok"],
            "tool_name": payload["tool_name"],
            "summary": payload["summary"],
            "data": payload["data"],
            "error_code": payload["error_code"],
            "error_message": payload["error_message"],
            "dry_run": payload["dry_run"],
            "request_id": payload["request_id"],
            "affected_entities_count": payload["affected_entities_count"],
        }
