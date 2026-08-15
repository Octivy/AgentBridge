"""Agent 现场演示：通过 AgentBridge 指挥四个宿主软件绘制图形。

流程与 MCP 客户端一致：读场景 → 写工具 dry-run（拿票据）→ 提交（自动授权，
reversible_write 无需人工确认）。所有对象带 AB-Demo- 前缀，并回显回滚令牌。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "copilot_backend"))

from host_mcp.runtime import HostMcpExecutor  # noqa: E402

READS = {
    "autocad": ("autocad_get_drawing_snapshot", {}),
    "blender": ("blender_scene_summary", {}),
    "rhino": ("rhino_scene_summary", {}),
    "sketchup": ("sketchup_scene_summary", {}),
}

WRITES = {
    "autocad": ("autocad_draw_line", {"start": [0, 0, 0], "end": [6, 4, 0], "layer": "0"}),
    "blender": ("blender_create_cube", {"name": "AB-Demo-Cube", "size": 1, "location": [0, 0, 0]}),
    "rhino": ("rhino_create_box", {"name": "AB-Demo-Box", "size": [1, 1, 1], "location": [2, 2, 0], "layer": "Demo"}),
    "sketchup": ("sketchup_create_box", {"name": "AB-Demo-Box", "size": [1, 1, 1], "location": [4, 4, 0]}),
}


def main() -> None:
    executor = HostMcpExecutor()
    tools = set(executor.tool_names())
    for kind in ("autocad", "blender", "rhino", "sketchup"):
        read_name, read_args = READS[kind]
        write_name, write_args = WRITES[kind]
        print("=" * 60)
        print(f"[{kind}]")
        if read_name not in tools:
            print(f"  READ {read_name} 不可用（宿主不在线？）")
            continue
        read = executor.execute_tool_sync(read_name, dict(read_args))
        summary = str(read.get("summary") or "")[:120]
        print(f"  READ {read_name}: ok={read.get('ok')} {summary}")

        if write_name not in tools:
            print(f"  WRITE {write_name} 不可用")
            continue
        preview = executor.execute_tool_sync(write_name, dict(write_args))
        token = preview.get("permission_token")
        if preview.get("ok") and token:
            commit = executor.execute_tool_sync(
                write_name,
                dict(write_args, dry_run=False, permission_token=token, preview_hash=preview.get("preview_hash") or ""),
            )
            print(f"  WRITE {write_name}: ok={commit.get('ok')} rollback_token={commit.get('rollback_token')}")
            if not commit.get("ok"):
                print(f"    error: {commit.get('error_code')} {commit.get('error_message')}")
        else:
            print(f"  WRITE {write_name} dry-run 失败: {preview.get('error_code')} {preview.get('error_message')}")


if __name__ == "__main__":
    main()
