from dataclasses import dataclass
from enum import Enum

from harness.tools import HarnessRiskLevel


class ApprovalPolicy(str, Enum):
    ASK = "ask"
    EXECUTE = "execute"
    FULL = "full"
    PLAN = "plan"


class PermissionBehavior(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionEvaluation:
    behavior: PermissionBehavior
    reason: str


def normalize_approval_policy(value: str | None) -> ApprovalPolicy:
    normalized = (value or "ask").strip().lower()
    if normalized in {"annotate", "request", "request_approval", "ask"}:
        return ApprovalPolicy.ASK
    if normalized in {"execute", "run_for_me"}:
        return ApprovalPolicy.EXECUTE
    if normalized in {"full", "full_approval"}:
        return ApprovalPolicy.FULL
    if normalized == "plan":
        return ApprovalPolicy.PLAN
    return ApprovalPolicy.ASK


def evaluate_permission(
    approval_policy: ApprovalPolicy,
    risk_level: HarnessRiskLevel | str,
    *,
    dry_run: bool,
) -> PermissionEvaluation:
    risk = _normalize_risk_level(risk_level)

    if risk in {HarnessRiskLevel.READ_ONLY, HarnessRiskLevel.PREVIEW_ONLY}:
        return PermissionEvaluation(PermissionBehavior.ALLOW, "safe_or_preview")

    if approval_policy == ApprovalPolicy.PLAN and not dry_run:
        return PermissionEvaluation(PermissionBehavior.DENY, "plan_mode_blocks_real_write")

    if risk in {
        HarnessRiskLevel.DESTRUCTIVE_WRITE,
        HarnessRiskLevel.EXTERNAL_SIDE_EFFECT,
        HarnessRiskLevel.CRITICAL,
    }:
        return PermissionEvaluation(PermissionBehavior.ASK, "destructive_or_critical_requires_approval")

    if approval_policy == ApprovalPolicy.ASK:
        return PermissionEvaluation(PermissionBehavior.ASK, "write_requires_user_approval")

    return PermissionEvaluation(PermissionBehavior.ALLOW, "approved_by_policy")


def _normalize_risk_level(value: HarnessRiskLevel | str) -> HarnessRiskLevel:
    if isinstance(value, HarnessRiskLevel):
        return value
    try:
        return HarnessRiskLevel(str(value or HarnessRiskLevel.CRITICAL.value))
    except ValueError:
        return HarnessRiskLevel.CRITICAL
