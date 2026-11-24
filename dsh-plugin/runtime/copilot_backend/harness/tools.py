from dataclasses import dataclass, field
from enum import Enum


class HarnessRiskLevel(str, Enum):
    READ_ONLY = "read_only"
    PREVIEW_ONLY = "preview_only"
    REVERSIBLE_WRITE = "reversible_write"
    DESTRUCTIVE_WRITE = "destructive_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    CRITICAL = "critical"


class HarnessCollapsePolicy(str, Enum):
    COLLAPSE_READ = "collapse_read"
    EXPANDED_ON_WRITE = "expanded_on_write"
    EXPANDED_ON_ERROR = "expanded_on_error"
    NEVER_COLLAPSE = "never_collapse"


@dataclass(frozen=True)
class HarnessToolMetadata:
    tool_name: str
    display_name: str
    category: str = "general"
    domain: str = "cad.general"
    risk_level: HarnessRiskLevel = HarnessRiskLevel.CRITICAL
    dry_run_supported: bool = False
    transaction_required: bool = False
    rollback_supported: bool = False
    permission_scope: str = "session"
    collapse_policy: HarnessCollapsePolicy = HarnessCollapsePolicy.EXPANDED_ON_ERROR
    ui_preview_kind: str = "none"
    model_visibility: str = "default"
    audit_required: bool = True
    domain_tags: tuple[str, ...] = field(default_factory=tuple)
