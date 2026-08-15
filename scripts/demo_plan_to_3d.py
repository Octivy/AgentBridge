"""平面图 → 3D 墙体 现场演示：读 AutoCAD 墙线 → 在 Rhino 生成墙体并合并。

流程与 MCP 客户端一致：读快照 → 提取墙线（双线合并成墙中心线）→
    rhino_create_box 逐墙 dry-run + 提交 → rhino_union_layer 合并为整体。
坐标：CAD 毫米 → 米（÷1000），并平移到原点附近；层高 3.0m、墙厚 0.24m。
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "copilot_backend"))

from host_mcp.runtime import HostMcpExecutor  # noqa: E402

FLOOR_HEIGHT = 3.0  # 层高（米）
WALL_THICKNESS = 0.24  # 墙厚（米）
MIN_WALL_LENGTH = 0.8  # 短于此长度的碎线跳过（门窗洞口/断线）
MAX_WALLS = 300  # 最多生成的墙段数（防止海量小块）
TARGET_LAYER = "AB-Plan-Walls"
TARGET_COLOR = "#C8A078"


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def extract_wall_lines(snapshot):
    """从快照取墙线：WALL 层 + 图层名含「墙」的 Line 实体，返回 (start, end) 列表。"""

    entities = snapshot.get("entities") or []
    lines = []
    for entity in entities:
        if entity.get("type") != "Line":
            continue
        layer = entity.get("layer") or ""
        if layer != "WALL" and "墙" not in layer:
            continue
        start = entity.get("start")
        end = entity.get("end")
        if not start or not end:
            continue
        lines.append((start, end))
    return lines


def to_meters(lines, origin):
    """CAD 毫米 → 米，并平移到原点附近。"""

    result = []
    for start, end in lines:
        a = [(start[0] - origin[0]) / 1000.0, (start[1] - origin[1]) / 1000.0]
        b = [(end[0] - origin[0]) / 1000.0, (end[1] - origin[1]) / 1000.0]
        result.append((a, b))
    return result


def merge_double_lines(lines):
    """把双线墙（墙两侧各一条平行线）合并为墙中心线。

    判定：同向（水平/垂直）、垂直间距 0.08~0.40m、沿线重叠 > 60% → 合并。
    返回 (centerlines, skipped_diagonal)。
    """

    used = [False] * len(lines)
    centerlines = []
    skipped_diagonal = 0
    for i, (a1, b1) in enumerate(lines):
        if used[i]:
            continue
        dx, dy = b1[0] - a1[0], b1[1] - a1[1]
        length = math.hypot(dx, dy)
        if length < MIN_WALL_LENGTH:
            continue
        horizontal = abs(dy) <= abs(dx)
        # 只处理正交墙；斜墙跳过（Rhino 盒子工具暂不支持旋转）
        if not (abs(dx) < 1e-6 or abs(dy) < 1e-6):
            skipped_diagonal += 1
            continue
        c1 = ((a1[0] + b1[0]) / 2.0, (a1[1] + b1[1]) / 2.0)
        mate = None
        for j in range(i + 1, len(lines)):
            if used[j]:
                continue
            a2, b2 = lines[j]
            d2x, d2y = b2[0] - a2[0], b2[1] - a2[1]
            if horizontal != (abs(d2y) <= abs(d2x)):
                continue
            if horizontal and (abs(d2y) > 1e-6 or abs(dy) > 1e-6):
                continue
            if not horizontal and (abs(d2x) > 1e-6 or abs(dx) > 1e-6):
                continue
            c2 = ((a2[0] + b2[0]) / 2.0, (a2[1] + b2[1]) / 2.0)
            gap = abs(c1[1] - c2[1]) if horizontal else abs(c1[0] - c2[0])
            if not (0.08 <= gap <= 0.40):
                continue
            # 沿线方向的重叠长度
            if horizontal:
                overlap = min(b1[0], b2[0]) - max(a1[0], a2[0])
            else:
                overlap = min(b1[1], b2[1]) - max(a1[1], a2[1])
            length2 = math.hypot(d2x, d2y)
            if overlap >= 0.6 * min(length, length2):
                mate = j
                break
        if mate is not None:
            a2, b2 = lines[mate]
            if horizontal:
                new_len = (max(b1[0], b2[0]) - min(a1[0], a2[0]), WALL_THICKNESS)
                center = ((min(a1[0], a2[0]) + max(b1[0], b2[0])) / 2.0, (c1[1] + c2[1]) / 2.0)
            else:
                new_len = (WALL_THICKNESS, max(b1[1], b2[1]) - min(a1[1], a2[1]))
                center = ((c1[0] + c2[0]) / 2.0, (min(a1[1], a2[1]) + max(b1[1], b2[1])) / 2.0)
            centerlines.append((new_len, center))
            used[mate] = True
        else:
            if horizontal:
                new_len = (length, WALL_THICKNESS)
                center = c1
            else:
                new_len = (WALL_THICKNESS, length)
                center = c1
            centerlines.append((new_len, center))
        used[i] = True
    return centerlines, skipped_diagonal


def create_walls(executor, centerlines):
    """逐墙 dry-run → 提交，返回成功数。"""

    ok = 0
    failed = 0
    for index, ((sx, sy), (cx, cy)) in enumerate(centerlines[:MAX_WALLS]):
        name = f"AB-Wall-{index:03d}"
        args = {
            "name": name,
            "size": [sx, sy, FLOOR_HEIGHT],
            "location": [cx, cy, FLOOR_HEIGHT / 2.0],
            "layer": TARGET_LAYER,
            "layer_color": TARGET_COLOR,
        }
        preview = executor.execute_tool_sync("rhino_create_box", dict(args))
        token = preview.get("permission_token")
        if preview.get("ok") and token:
            commit = executor.execute_tool_sync(
                "rhino_create_box",
                dict(args, dry_run=False, permission_token=token, preview_hash=preview.get("preview_hash") or ""),
            )
            if commit.get("ok"):
                ok += 1
            else:
                failed += 1
                print(f"  {name} 失败: {commit.get('error_code')} {commit.get('error_message')}")
        else:
            failed += 1
            print(f"  {name} dry-run 失败: {preview.get('error_code')} {preview.get('error_message')}")
    return ok, failed


def main() -> None:
    executor = HostMcpExecutor()
    tools = set(executor.tool_names())
    print("=" * 60)
    print("[1] 读取 AutoCAD 平面图快照…")
    read = executor.execute_tool_sync("autocad_get_drawing_snapshot", {})
    if not read.get("ok"):
        print(f"  读取失败: {read.get('error_code')} {read.get('error_message')}")
        return
    snapshot = read["data"]["snapshot"]
    summary = snapshot["drawing_summary"]
    print(f"  实体 {summary['total_entities']} 个 · 图层 {summary['total_layers']} 个 · 图框 {summary['detected_frames']} 个")
    print(f"  图纸范围: {summary['bounds']['min']} ~ {summary['bounds']['max']}（毫米）")

    print("[2] 提取墙线（WALL 层 + 含「墙」图层）…")
    raw = extract_wall_lines(snapshot)
    print(f"  找到墙线 {len(raw)} 条")

    print("[3] 坐标换算：毫米 → 米，平移至原点附近…")
    origin = summary["bounds"]["min"]
    lines = to_meters(raw, origin)
    print(f"  图纸约 {(summary['bounds']['max'][0] - summary['bounds']['min'][0]) / 1000:.1f}m × "
          f"{(summary['bounds']['max'][1] - summary['bounds']['min'][1]) / 1000:.1f}m")

    print("[4] 双线墙合并为墙中心线…")
    centerlines, diagonal = merge_double_lines(lines)
    print(f"  墙中心线 {len(centerlines)} 段（斜墙跳过 {diagonal} 条，Rhino 盒子暂不支持旋转）")

    print("[5] 在 Rhino 中逐墙生成盒子（层高 3.0m，墙厚 0.24m）…")
    ok, failed = create_walls(executor, centerlines)
    print(f"  成功 {ok} 段墙体 · 失败 {failed} 段 · 图层 {TARGET_LAYER}")

    if ok and "rhino_union_layer" in tools:
        print("[6] 合并墙体为整体（布尔并集，消除内部交接线）…")
        union = executor.execute_tool_sync("rhino_union_layer", {"layer": TARGET_LAYER})
        print(f"  合并: ok={union.get('ok')} {union.get('error_message') or ''}")
    else:
        print("[6] 跳过合并（无墙或工具不可用）")

    print("=" * 60)
    print(f"完成：平面图墙线 → Rhino 3D 墙体 {ok} 段。可整层回滚：删除图层 {TARGET_LAYER}。")


if __name__ == "__main__":
    main()
