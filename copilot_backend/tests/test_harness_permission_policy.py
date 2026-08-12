import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.permissions import ApprovalPolicy, PermissionBehavior, evaluate_permission
from harness.tools import HarnessRiskLevel


def test_read_only_is_allowed_in_all_modes():
    result = evaluate_permission(ApprovalPolicy.ASK, HarnessRiskLevel.READ_ONLY, dry_run=False)

    assert result.behavior == PermissionBehavior.ALLOW


def test_ask_mode_requires_permission_for_reversible_write():
    result = evaluate_permission(ApprovalPolicy.ASK, HarnessRiskLevel.REVERSIBLE_WRITE, dry_run=True)

    assert result.behavior == PermissionBehavior.ASK
    assert result.reason == "write_requires_user_approval"


def test_execute_mode_allows_reversible_write_after_preview():
    result = evaluate_permission(ApprovalPolicy.EXECUTE, HarnessRiskLevel.REVERSIBLE_WRITE, dry_run=False)

    assert result.behavior == PermissionBehavior.ALLOW


def test_full_mode_still_asks_for_destructive_write():
    result = evaluate_permission(ApprovalPolicy.FULL, HarnessRiskLevel.DESTRUCTIVE_WRITE, dry_run=False)

    assert result.behavior == PermissionBehavior.ASK
    assert result.reason == "destructive_or_critical_requires_approval"


def test_plan_mode_denies_real_write():
    result = evaluate_permission(ApprovalPolicy.PLAN, HarnessRiskLevel.REVERSIBLE_WRITE, dry_run=False)

    assert result.behavior == PermissionBehavior.DENY
    assert result.reason == "plan_mode_blocks_real_write"
