from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommitPolicyDecision:
    allowed: bool
    error_code: str = ""
    message: str = ""


def evaluate_commit_policy(
    risk_level: str,
    *,
    confirmed_by_local_user: bool,
    task_id: str,
) -> CommitPolicyDecision:
    risk = str(risk_level or "critical").strip().lower()
    if risk in {"read_only", "preview_only"}:
        return CommitPolicyDecision(False, "write_not_allowed", "This tool is not a commit-capable write tool.")
    if risk == "reversible_write":
        return CommitPolicyDecision(True)
    if risk == "destructive_write":
        if not confirmed_by_local_user:
            return CommitPolicyDecision(
                False,
                "local_confirmation_required",
                "Destructive CAD writes require explicit confirmation by the local user.",
            )
        return CommitPolicyDecision(True)
    if risk in {"critical", "external_side_effect"}:
        if not confirmed_by_local_user:
            return CommitPolicyDecision(
                False,
                "local_confirmation_required",
                "Critical operations require explicit confirmation by the local user.",
            )
        if not str(task_id or "").strip():
            return CommitPolicyDecision(
                False,
                "task_context_required",
                "Critical operations require a non-empty task_id for audit correlation.",
            )
        return CommitPolicyDecision(True)
    return CommitPolicyDecision(False, "unsupported_risk_level", f"Unsupported risk level: {risk}")


__all__ = ["CommitPolicyDecision", "evaluate_commit_policy"]
