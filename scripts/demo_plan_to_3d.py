"""平面图 → 3D 墙体 现场演示（v2）：读 AutoCAD 墙线 → Rhino 墙体（真实墙厚 + 门窗开洞）。

相比 v1 的改进：
- 墙厚不再固定 0.24m，而是取自每道双线墙的实际间距（单线墙用图纸主流墙厚）；
- 识别门窗：WINDOW 层的线（线长=窗宽）与 DOOR_FIRE 层的块插入点（比例=门宽），
  在对应墙体上开出洞口；
- 重跑前自动清理 Rhino 中上一版的 AB-Plan-Walls 图层对象（幂等）。

流程与 MCP 客户端一致：读快照 → 几何分析（全部在 Agent 侧完成）→
    rhino_create_box 逐段 dry-run + 提交 → rhino_union_layer 合并为整体。
坐标：CAD 毫米 → 米（÷1000），平移到原点附近；层高 3.0m。
"""

import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "copilot_backend"))

from host_mcp.runtime import HostMcpExecutor  # noqa: E402

FLOOR_HEIGHT = 3.0  # 层高（米）
MIN_WALL_LENGTH = 0.8  # 短于此长度的碎线跳过
MIN_SEGMENT = 0.1  # 开洞后短于此长度的残段丢弃（米）
MAX_SEGMENTS = 500  # 最多生成的墙段数
TARGET_LAYER = "AB-Plan-Walls"
TARGET_COLOR = "#C8A078"


def _mid(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def to_meters_pair(start, end, origin):
    return (
        [(start[0] - origin[0]) / 1000.0, (start[1] - origin[1]) / 1000.0],
        [(end[0] - origin[0]) / 1000.0, (end[1] - origin[1]) / 1000.0],
    )


def extract_entities(snapshot, origin):
    """按图层分类：墙线（含「墙」）、窗线（WINDOW 层 Line）、门块（DOOR_FIRE 层 BlockReference/Line）。"""

    wall_lines = []
    window_lines = []
    door_blocks = []
    for entity in snapshot.get("entities") or []:
        layer = entity.get("layer") or ""
        etype = entity.get("type")
        if etype == "Line" and (layer == "WALL" or "墙" in layer):
            if entity.get("start") and entity.get("end"):
                wall_lines.append(to_meters_pair(entity["start"], entity["end"], origin))
        elif etype == "Line" and layer == "WINDOW":
            if entity.get("start") and entity.get("end"):
                window_lines.append(to_meters_pair(entity["start"], entity["end"], origin))
        elif layer == "DOOR_FIRE" and etype == "BlockReference":
            if entity.get("position"):
                door_blocks.append(entity)
        elif etype == "Line" and layer == "DOOR_FIRE":
            if entity.get("start") and entity.get("end"):
                window_lines.append(to_meters_pair(entity["start"], entity["end"], origin))
    return wall_lines, window_lines, door_blocks


def build_walls(lines):
    """双线墙合并为墙中心线：墙厚取双线实际间距；单线墙用主流墙厚。

    返回 (walls, skipped_diagonal)。wall = {horiz, fixed, lo, hi, thickness}
    """

    used = [False] * len(lines)
    walls = []
    pair_gaps = []
    skipped_diagonal = 0
    for i, (a1, b1) in enumerate(lines):
        if used[i]:
            continue
        dx = b1[0] - a1[0]
        dy = b1[1] - a1[1]
        length = math.hypot(dx, dy)
        if length < MIN_WALL_LENGTH:
            continue
        if not (abs(dx) < 1e-6 or abs(dy) < 1e-6):
            skipped_diagonal += 1
            continue
        horiz = abs(dy) <= abs(dx)
        c1 = _mid(a1, b1)
        mate = None
        mate_gap = None
        for j in range(i + 1, len(lines)):
            if used[j]:
                continue
            a2, b2 = lines[j]
            d2x = b2[0] - a2[0]
            d2y = b2[1] - a2[1]
            if horiz != (abs(d2y) <= abs(d2x)):
                continue
            if horiz and (abs(dy) > 1e-6 or abs(d2y) > 1e-6):
                continue
            if not horiz and (abs(dx) > 1e-6 or abs(d2x) > 1e-6):
                continue
            c2 = _mid(a2, b2)
            gap = abs(c1[1] - c2[1]) if horiz else abs(c1[0] - c2[0])
            if not (0.05 <= gap <= 0.60):
                continue
            if horiz:
                overlap = min(b1[0], b2[0]) - max(a1[0], a2[0])
            else:
                overlap = min(b1[1], b2[1]) - max(a1[1], a2[1])
            length2 = math.hypot(d2x, d2y)
            if overlap >= 0.6 * min(length, length2):
                mate = j
                mate_gap = gap
                break
        if mate is not None:
            a2, b2 = lines[mate]
            c2 = _mid(a2, b2)
            pair_gaps.append(mate_gap)
            if horiz:
                walls.append(
                    {
                        "horiz": True,
                        "fixed": (c1[1] + c2[1]) / 2.0,
                        "lo": min(a1[0], a2[0]),
                        "hi": max(b1[0], b2[0]),
                        "thickness": mate_gap,
                    }
                )
            else:
                walls.append(
                    {
                        "horiz": False,
                        "fixed": (c1[0] + c2[0]) / 2.0,
                        "lo": min(a1[1], a2[1]),
                        "hi": max(b1[1], b2[1]),
                        "thickness": mate_gap,
                    }
                )
            used[mate] = True
        else:
            if horiz:
                walls.append(
                    {"horiz": True, "fixed": c1[1], "lo": min(a1[0], b1[0]), "hi": max(a1[0], b1[0]), "thickness": None}
                )
            else:
                walls.append(
                    {"horiz": False, "fixed": c1[0], "lo": min(a1[1], b1[1]), "hi": max(a1[1], b1[1]), "thickness": None}
                )
        used[i] = True
    default_t = statistics.median(pair_gaps) if pair_gaps else 0.24
    for wall in walls:
        if wall["thickness"] is None:
            wall["thickness"] = default_t
    return walls, skipped_diagonal, default_t


def extract_openings(window_lines, door_blocks, origin):
    """门窗洞口：窗线（线长=窗宽）、门块（比例=门宽、旋转=墙方向）。

    返回 openings = [{horiz, fixed, lo, hi, kind}]（单位：米）。
    """

    openings = []
    for start, end in window_lines:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if abs(dx) > 1e-6 and abs(dy) < 1e-6:
            openings.append(
                {"horiz": True, "fixed": start[1], "lo": min(start[0], end[0]), "hi": max(start[0], end[0]), "kind": "window"}
            )
        elif abs(dy) > 1e-6 and abs(dx) < 1e-6:
            openings.append(
                {"horiz": False, "fixed": start[0], "lo": min(start[1], end[1]), "hi": max(start[1], end[1]), "kind": "window"}
            )
    for block in door_blocks:
        position = block["position"]
        scale = block.get("scale") or [1000.0, 1000.0, 1.0]
        width = max(abs(scale[0]), abs(scale[1])) / 1000.0
        rotation = float(block.get("rotation") or 0.0)
        # 门扇方向 = 洞口展开方向（铰点 → 门扇端点）
        dx = math.cos(rotation)
        dy = math.sin(rotation)
        px = (position[0] - origin[0]) / 1000.0
        py = (position[1] - origin[1]) / 1000.0
        if abs(dx) >= abs(dy):
            span = width * (1.0 if dx >= 0 else -1.0)
            lo, hi = px, px + span
            if lo > hi:
                lo, hi = hi, lo
            openings.append({"horiz": True, "fixed": py, "lo": lo, "hi": hi, "kind": "door"})
        else:
            span = width * (1.0 if dy >= 0 else -1.0)
            lo, hi = py, py + span
            if lo > hi:
                lo, hi = hi, lo
            openings.append({"horiz": False, "fixed": px, "lo": lo, "hi": hi, "kind": "door"})
    return openings


def split_walls_by_openings(walls, openings):
    """把墙按洞口切成墙段。返回 (segments, applied_openings)。

    segment = {horiz, fixed, lo, hi, thickness}
    """

    applied = 0
    segments = []
    for wall in walls:
        tolerance = wall["thickness"] / 2.0 + 0.15
        cuts = []
        for opening in openings:
            if opening["horiz"] != wall["horiz"]:
                continue
            if abs(opening["fixed"] - wall["fixed"]) > tolerance:
                continue
            lo = max(opening["lo"], wall["lo"])
            hi = min(opening["hi"], wall["hi"])
            if hi - lo > 0.05:
                cuts.append((lo, hi))
                applied += 1
        cuts.sort()
        merged = []
        for lo, hi in cuts:
            if merged and lo <= merged[-1][1] + 0.01:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        cursor = wall["lo"]
        for lo, hi in merged:
            if lo - cursor > MIN_SEGMENT:
                segments.append(dict(wall, lo=cursor, hi=lo))
            cursor = max(cursor, hi)
        if wall["hi"] - cursor > MIN_SEGMENT:
            segments.append(dict(wall, lo=cursor, hi=wall["hi"]))
    return segments, applied


def cleanup_layer(executor, layer):
    """删除 Rhino 中上一版图层上的对象，保证重跑幂等。"""

    read = executor.execute_tool_sync("rhino_get_objects", {"layer": layer})
    data = read.get("data") or read.get("result") or {}
    objects = data.get("objects") or []
    deleted = 0
    for obj in objects:
        done = executor.execute_tool_sync("rhino_delete_object", {"object_id": obj["id"]})
        if done.get("ok"):
            deleted += 1
    return deleted, len(objects)


def create_segments(executor, segments):
    """逐段 dry-run → 提交盒子墙。"""

    ok = 0
    failed = 0
    for index, segment in enumerate(segments[:MAX_SEGMENTS]):
        length = segment["hi"] - segment["lo"]
        thickness = segment["thickness"]
        if segment["horiz"]:
            size = [length, thickness, FLOOR_HEIGHT]
            center = [(segment["lo"] + segment["hi"]) / 2.0, segment["fixed"], FLOOR_HEIGHT / 2.0]
        else:
            size = [thickness, length, FLOOR_HEIGHT]
            center = [segment["fixed"], (segment["lo"] + segment["hi"]) / 2.0, FLOOR_HEIGHT / 2.0]
        args = {
            "name": f"AB-Wall-{index:03d}",
            "size": size,
            "location": center,
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
                print(f"  {args['name']} 失败: {commit.get('error_code')} {commit.get('error_message')}")
        else:
            failed += 1
            print(f"  {args['name']} dry-run 失败: {preview.get('error_code')} {preview.get('error_message')}")
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
    origin = summary["bounds"]["min"]
    print(f"  实体 {summary['total_entities']} 个 · 图纸约 "
          f"{(summary['bounds']['max'][0] - summary['bounds']['min'][0]) / 1000:.1f}m × "
          f"{(summary['bounds']['max'][1] - summary['bounds']['min'][1]) / 1000:.1f}m")

    print("[2] 提取墙线 / 窗线 / 门块…")
    wall_lines, window_lines, door_blocks = extract_entities(snapshot, origin)
    print(f"  墙线 {len(wall_lines)} 条 · 窗线 {len(window_lines)} 条 · 门块 {len(door_blocks)} 个")

    print("[3] 双线墙合并为墙中心线（墙厚取实际间距）…")
    walls, diagonal, default_t = build_walls(wall_lines)
    print(f"  墙 {len(walls)} 道（斜墙跳过 {diagonal} 条）· 主流墙厚 {default_t * 1000:.0f}mm")

    print("[4] 门窗开洞（窗宽=窗线长，门宽=块比例）…")
    openings = extract_openings(window_lines, door_blocks, origin)
    segments, applied = split_walls_by_openings(walls, openings)
    print(f"  洞口 {len(openings)} 个（窗 {sum(1 for o in openings if o['kind'] == 'window')} / "
          f"门 {sum(1 for o in openings if o['kind'] == 'door')}）· 成功套用 {applied} 处 · 墙段 {len(segments)} 段")

    print("[5] 清理 Rhino 上一版 AB-Plan-Walls 图层…")
    deleted, total = cleanup_layer(executor, TARGET_LAYER)
    print(f"  删除旧对象 {deleted}/{total} 个")

    print("[6] 在 Rhino 中逐段生成墙体（层高 3.0m，真实墙厚）…")
    ok, failed = create_segments(executor, segments)
    print(f"  成功 {ok} 段墙体 · 失败 {failed} 段 · 图层 {TARGET_LAYER}")

    if ok and "rhino_union_layer" in tools:
        print("[7] 合并墙体为整体（布尔并集，消除内部交接线）…")
        union = executor.execute_tool_sync("rhino_union_layer", {"layer": TARGET_LAYER})
        print(f"  合并: ok={union.get('ok')} {union.get('error_message') or ''}")
    else:
        print("[7] 跳过合并（无墙或工具不可用）")

    print("=" * 60)
    print(f"完成：平面图 → Rhino 3D 墙体 {ok} 段（含门窗洞口）。可整层回滚：删除图层 {TARGET_LAYER}。")


if __name__ == "__main__":
    main()
