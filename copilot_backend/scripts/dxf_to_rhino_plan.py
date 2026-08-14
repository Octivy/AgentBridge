"""AgentBridge：天正 DXF 图纸 → Rhino 墙体建模管线。

用法：
    python dxf_to_rhino_plan.py <图纸.dxf> [--dry] [--step-delay 0]
                                [--wall-height 3.0] [--update]

支持两种图纸：
- T3 导出（推荐）：天正把自定义对象炸成普通 LINE/INSERT，
  WALL 层双线墙 -> 配对重建中心线；
- 原始 TCH：解析 TDbWall 字符串重建墙网格（回退）。

建模规则：
- 同轴墙段合并、端点向相邻垂直墙延伸（T 型交接闭合）；
- 门窗在墙上开洞：断墙 + 过梁（+窗台），洞口内放门/窗薄片标记；
- 分层：墙/柱/门/窗 各自独立图层并上色；
- --update：与上次构建记录对比，只增删改差异，不清空重建。
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import time
import urllib.request
from collections import defaultdict

import ezdxf
from ezdxf.lldxf.tagger import ascii_tags_loader


WALL_THICKNESS_MM = 200.0
VERTICAL_SNAP_MM = 400.0
T3_PAIR_MIN_MM = 80.0
T3_PAIR_MAX_MM = 650.0
JUNCTION_TOL_MM = 700.0
ATTACH_TOL_MM = 100.0

LAYER_WALL = ("墙", "C9C9C9")
LAYER_COLUMN = ("柱", "FF0000")
LAYER_DOOR = ("门", "FF8000")
LAYER_WINDOW = ("窗", "00A2E8")

DOOR_HEIGHT_M = 2.2
WINDOW_SILL_M = 0.9
WINDOW_HEIGHT_M = 1.5

CORRECTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_corrections.json")


def _decode300(value: str):
    try:
        raw = base64.b64decode(value)
        text = raw.decode("utf-16-le", errors="replace")
        return [float(x) for x in text.replace("\x00", "").split(",") if x.strip()]
    except Exception:
        return None


def _parse_walls(path: str):
    horizontals = []
    vertical_pts = defaultdict(list)
    cur = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for tag in ascii_tags_loader(fh):
            if tag.code == 0:
                cur = {} if tag.value == "TCH_WALL" else None
            elif cur is not None and tag.code == 300:
                nums = _decode300(tag.value)
                if not nums or len(nums) < 4:
                    continue
                x1, x2, y1, y2 = nums[0], nums[1], nums[2], nums[3]
                if abs(x2 - x1) > 1.0:
                    horizontals.append((min(x1, x2), max(x1, x2), y1))
                elif abs(y2 - y1) > 1.0:
                    vertical_pts[round(x1, 1)].append((min(y1, y2), max(y1, y2)))
                else:
                    vertical_pts[round(x1, 1)].append(round(y1, 1))
    return horizontals, vertical_pts


def _read_openings(path: str):
    openings = []
    cur = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for tag in ascii_tags_loader(fh):
            if tag.code == 0:
                if tag.value == "TCH_OPENING":
                    cur = {"tags": []}
                    openings.append(cur)
                else:
                    cur = None
            elif cur is not None:
                cur["tags"].append((tag.code, tag.value))
    result = []
    for op in openings:
        tags = dict(op["tags"])
        try:
            p1 = (float(tags[10]), float(tags[20]))
        except Exception:
            continue
        width = float(tags.get(40) or 0.0)
        height = float(tags.get(41) or 0.0)
        layer = str(tags.get(8) or "")
        angle = float(tags.get(50) or 0.0)
        kind = "door" if "DOOR" in layer.upper() else "window"
        result.append(
            {
                "kind": kind,
                "layer": layer,
                "width_mm": width,
                "height_mm": height,
                "p1": p1,
                "angle": angle,
            }
        )
    return result


def _read_columns(path: str):
    columns = []
    cur = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for tag in ascii_tags_loader(fh):
            if tag.code == 0:
                if tag.value == "TCH_COLUMN":
                    cur = {"tags": []}
                    columns.append(cur)
                else:
                    cur = None
            elif cur is not None:
                cur["tags"].append((tag.code, tag.value))
    result = []
    for col in columns:
        tags = dict(col["tags"])
        try:
            cx = float(tags[11])
            cy = float(tags[21])
        except Exception:
            continue
        height = float(tags.get(149) or 3000.0)
        xs = [float(v) for code, v in col["tags"] if code == 10]
        ys = [float(v) for code, v in col["tags"] if code == 20]
        if not xs or not ys:
            continue
        result.append(
            {
                "cx_mm": cx,
                "cy_mm": cy,
                "dx_mm": max(xs) - min(xs),
                "dy_mm": max(ys) - min(ys),
                "height_mm": height,
            }
        )
    return result


def _merge_segments(segments):
    out = []
    for a, b in sorted(segments):
        if not out or a > out[-1][1] + 1.0:
            out.append([a, b])
        else:
            out[-1][1] = max(out[-1][1], b)
    return [(a, b) for a, b in out]


def _pair_centerlines(by_level):
    merged = {level: _merge_segments(runs) for level, runs in by_level.items()}
    centerlines = []
    used = set()
    for level, runs in merged.items():
        for (a, b) in runs:
            best = None
            for level2, runs2 in merged.items():
                if level2 == level:
                    continue
                distance = abs(level2 - level)
                if distance < T3_PAIR_MIN_MM or distance > T3_PAIR_MAX_MM:
                    continue
                for (a2, b2) in runs2:
                    overlap = min(b, b2) - max(a, a2)
                    if overlap <= 0:
                        continue
                    ratio = overlap / min(b - a, b2 - a2)
                    if ratio < 0.5:
                        continue
                    score = (ratio, -distance)
                    if best is None or score > best[0]:
                        best = (score, level2, a2, b2)
            if best is not None:
                _, level2, a2, b2 = best
                xa, xb = max(a, a2), min(b, b2)
                fixed = (level + level2) / 2.0
                thickness = abs(level2 - level)
                centerlines.append((xa, xb, fixed, thickness))
                used.add((level, a, b))
                used.add((level2, a2, b2))
    for level, runs in merged.items():
        for (a, b) in runs:
            if (level, a, b) not in used and (b - a) > 100.0:
                centerlines.append((a, b, level, WALL_THICKNESS_MM))
    return centerlines


def _parse_t3(doc):
    msp = doc.modelspace()
    h_by_y = {}
    v_by_x = {}
    for entity in msp:
        if entity.dxftype() != "LINE" or entity.dxf.layer != "WALL":
            continue
        s, t = entity.dxf.start, entity.dxf.end
        if abs(s[1] - t[1]) < 1e-3:
            h_by_y.setdefault(round(s[1], 1), []).append((min(s[0], t[0]), max(s[0], t[0])))
        elif abs(s[0] - t[0]) < 1e-3:
            v_by_x.setdefault(round(s[0], 1), []).append((min(s[1], t[1]), max(s[1], t[1])))

    segments = []
    for xa, xb, ymid, thick in _pair_centerlines(h_by_y):
        segments.append({"kind": "h", "x1": xa, "x2": xb, "y1": ymid, "y2": ymid, "thick": thick})
    for ya, yb, xmid, thick in _pair_centerlines(v_by_x):
        segments.append({"kind": "v", "x1": xmid, "x2": xmid, "y1": ya, "y2": yb, "thick": thick})

    columns = []
    for entity in msp:
        if entity.dxftype() != "INSERT" or entity.dxf.layer != "COLUMN":
            continue
        try:
            sx = abs(float(entity.dxf.xscale))
            sy = abs(float(entity.dxf.yscale))
        except Exception:
            sx = sy = 600.0
        pos = entity.dxf.insert
        columns.append(
            {
                "cx_mm": pos[0],
                "cy_mm": pos[1],
                "dx_mm": sx,
                "dy_mm": sy,
                "height_mm": 3000.0,
            }
        )

    openings = []
    for entity in msp:
        if entity.dxftype() != "INSERT":
            continue
        layer = entity.dxf.layer
        if layer not in ("WINDOW", "DOOR_FIRE"):
            continue
        try:
            width = abs(float(entity.dxf.xscale))
            rotation = float(getattr(entity.dxf, "rotation", 0.0))
        except Exception:
            width = 1000.0
            rotation = 0.0
        pos = entity.dxf.insert
        openings.append(
            {
                "kind": "door" if layer == "DOOR_FIRE" else "window",
                "layer": layer,
                "width_mm": width,
                "height_mm": 2100.0 if layer == "DOOR_FIRE" else 1500.0,
                "p1": (pos[0], pos[1]),
                "angle": rotation,
            }
        )
    return segments, columns, openings


def _snap(value: float, targets, tolerance: float) -> float:
    for target in targets:
        if abs(value - target) <= tolerance:
            return target
    return value


def reconstruct_segments(horizontals, vertical_pts):
    y_levels = sorted({round(h[2]) for h in horizontals})
    segments = []
    for xa, xb, y in horizontals:
        segments.append({"kind": "h", "x1": xa, "x2": xb, "y1": y, "y2": y, "thick": WALL_THICKNESS_MM})
    for x in sorted(vertical_pts):
        values = vertical_pts[x]
        if values and isinstance(values[0], tuple):
            for ya, yb in values:
                segments.append(
                    {"kind": "v", "x1": x, "x2": x, "y1": ya, "y2": yb, "thick": WALL_THICKNESS_MM}
                )
        else:
            ys = sorted(set(values))
            for ya, yb in zip(ys, ys[1:]):
                ya_s = _snap(ya, y_levels, VERTICAL_SNAP_MM)
                yb_s = _snap(yb, y_levels, VERTICAL_SNAP_MM)
                segments.append(
                    {"kind": "v", "x1": x, "x2": x, "y1": ya_s, "y2": yb_s, "thick": WALL_THICKNESS_MM}
                )
    return segments


def _apply_opening_corrections(openings, path=CORRECTIONS_PATH):
    """Apply project-level corrections (e.g. entrance drawn as window -> door).

    Positions are matched within 300mm so fractional DXF coordinates don't
    matter.  Returns a new list; each matched opening's kind is overridden.
    """
    if not os.path.exists(path):
        return openings
    try:
        with open(path, encoding="utf-8") as fh:
            corrections = json.load(fh).get("openings", [])
    except Exception:  # noqa: BLE001
        return openings
    out = []
    for op in openings:
        px, py = op["p1"]
        for corr in corrections:
            try:
                cx, cy = corr["position"]
            except Exception:  # noqa: BLE001
                continue
            if abs(px - cx) <= 300 and abs(py - cy) <= 300:
                op = dict(op)
                op["kind"] = corr.get("kind", op["kind"])
                break
        out.append(op)
    return out


def _merge_walls(h_walls, v_walls):
    def merge(walls):
        groups = {}
        for fixed, thick, a, b in walls:
            groups.setdefault((round(fixed, 1), round(thick, 1)), []).append((a, b))
        out = []
        for (fixed, thick), runs in groups.items():
            for a, b in _merge_segments(runs):
                if b - a >= 100.0:
                    out.append((fixed, thick, a, b))
        return out

    return merge(h_walls), merge(v_walls)


def _cap_low(a, target, bounds):
    """Cap a downward/leftward extension from ``a`` toward ``target``."""
    best = target
    for oa, ob in bounds:
        if oa <= a and ob >= target:
            if ob >= a:
                return a
            best = max(best, ob)
    return max(target, min(a, best))


def _cap_high(b, target, bounds):
    """Cap an upward/rightward extension from ``b`` toward ``target``."""
    best = target
    for oa, ob in bounds:
        if oa <= target and ob >= b:
            if oa <= b:
                return b
            best = min(best, oa)
    return max(b, min(target, best))


def _extend_junctions(h_walls, v_walls, h_bounds=None, v_bounds=None, tol=JUNCTION_TOL_MM):
    """Extend each wall endpoint through the crossing wall (to its far face).

    Only crossing walls whose span actually overlaps this wall's thickness
    band are considered, so parallel walls offset by a corridor are never
    merged.  Extensions stop at opening-zone edges (``h_bounds``/``v_bounds``
    map a line's fixed coordinate to its opening zones), so a wall never gets
    extended into a door or window opening.
    """
    h_bounds = h_bounds or {}
    v_bounds = v_bounds or {}

    def overlaps(a1, a2, b1, b2):
        return a1 < b2 and b1 < a2

    out_h = []
    for y, thick, a, b in h_walls:
        band_lo, band_hi = y - thick / 2.0, y + thick / 2.0
        crossing = [w for w in v_walls if overlaps(w[2], w[3], band_lo, band_hi)]
        bounds = h_bounds.get(round(y, 1), [])
        below = [w for w in crossing if w[0] <= a and a - w[0] <= tol]
        if below:
            w = max(below, key=lambda item: item[0])
            a = _cap_low(a, w[0] - w[1] / 2.0, bounds)
        above = [w for w in crossing if w[0] >= b and w[0] - b <= tol]
        if above:
            w = min(above, key=lambda item: item[0])
            b = _cap_high(b, w[0] + w[1] / 2.0, bounds)
        out_h.append((y, thick, a, b))
    out_v = []
    for x, thick, a, b in v_walls:
        band_lo, band_hi = x - thick / 2.0, x + thick / 2.0
        crossing = [w for w in out_h if overlaps(w[2], w[3], band_lo, band_hi)]
        bounds = v_bounds.get(round(x, 1), [])
        below = [w for w in crossing if w[0] <= a and a - w[0] <= tol]
        if below:
            w = max(below, key=lambda item: item[0])
            a = _cap_low(a, w[0] - w[1] / 2.0, bounds)
        above = [w for w in crossing if w[0] >= b and w[0] - b <= tol]
        if above:
            w = min(above, key=lambda item: item[0])
            b = _cap_high(b, w[0] + w[1] / 2.0, bounds)
        out_v.append((x, thick, a, b))
    return out_h, out_v


def _attach_openings(h_walls, v_walls, openings, tol=ATTACH_TOL_MM):
    attached = []
    for op in openings:
        px, py = op["p1"]
        width = op["width_mm"] or 1000.0
        best = None
        for y, thick, a, b in h_walls:
            if abs(py - y) <= 300 and (a - width / 2 - tol) <= px <= (b + width / 2 + tol):
                if best is None or abs(py - y) < best[0]:
                    best = (abs(py - y), ("h", y, thick, a, b), px)
        for x, thick, a, b in v_walls:
            if abs(px - x) <= 300 and (a - width / 2 - tol) <= py <= (b + width / 2 + tol):
                if best is None or abs(px - x) < best[0]:
                    best = (abs(px - x), ("v", x, thick, a, b), py)
        if best is not None:
            attached.append((best[1], best[2], op))
    return attached


def _emit_wall_box(boxes, is_h, fixed, thick, pa, pb, wall_height, ox, oy):
    H = wall_height
    wall_layer, wall_color = LAYER_WALL
    if is_h:
        size = ((pb - pa) / 1000.0, thick / 1000.0, H)
        loc = (((pa + pb) / 2.0 - ox) / 1000.0, (fixed - oy) / 1000.0, H / 2.0)
        name = "墙-H-%.0f-%.0f-%.0f" % (fixed, pa, pb)
    else:
        size = (thick / 1000.0, (pb - pa) / 1000.0, H)
        loc = ((fixed - ox) / 1000.0, ((pa + pb) / 2.0 - oy) / 1000.0, H / 2.0)
        name = "墙-V-%.0f-%.0f-%.0f" % (fixed, pa, pb)
    boxes.append(
        {"name": name, "layer": wall_layer, "layer_color": wall_color, "size": size, "location": loc}
    )


def _emit_opening(boxes, is_h, fixed, thick, pos, op, wall_height, ox, oy):
    """Emit the lintel/sill and door/window marker for one attached opening."""
    H = wall_height
    w = op["width_mm"]
    kind = op["kind"]
    height = DOOR_HEIGHT_M if kind == "door" else WINDOW_HEIGHT_M
    sill = 0.0 if kind == "door" else WINDOW_SILL_M
    lintel_h = H - (sill + height)
    if is_h:
        # 水平墙：开孔沿 x 方向（pos 是 x），墙线固定在 y（fixed）。
        lx = (pos - ox) / 1000.0
        ly = (fixed - oy) / 1000.0
    else:
        # 竖直墙：开孔沿 y 方向（pos 是 y），墙线固定在 x（fixed）。
        lx = (fixed - ox) / 1000.0
        ly = (pos - oy) / 1000.0
    if lintel_h > 0.05:
        z = sill + height + lintel_h / 2.0
        if is_h:
            size = (w / 1000.0, thick / 1000.0, lintel_h)
            loc = (lx, ly, z)
            name = "楣-H-%.0f-%.0f" % (fixed, pos)
        else:
            size = (thick / 1000.0, w / 1000.0, lintel_h)
            loc = (lx, ly, z)
            name = "楣-V-%.0f-%.0f" % (fixed, pos)
        boxes.append(
            {"name": name, "layer": LAYER_WALL[0], "layer_color": LAYER_WALL[1], "size": size, "location": loc}
        )
    if kind == "window" and sill > 0.05:
        if is_h:
            size = (w / 1000.0, thick / 1000.0, sill)
            loc = (lx, ly, sill / 2.0)
            name = "台-H-%.0f-%.0f" % (fixed, pos)
        else:
            size = (thick / 1000.0, w / 1000.0, sill)
            loc = (lx, ly, sill / 2.0)
            name = "台-V-%.0f-%.0f" % (fixed, pos)
        boxes.append(
            {"name": name, "layer": LAYER_WALL[0], "layer_color": LAYER_WALL[1], "size": size, "location": loc}
        )
    z = sill + height / 2.0
    if is_h:
        size = (w / 1000.0, 0.08, height)
        loc = (lx, ly, z)
    else:
        size = (0.08, w / 1000.0, height)
        loc = (lx, ly, z)
    layer, color = LAYER_DOOR if kind == "door" else LAYER_WINDOW
    name = ("门-%.0f-%.0f" if kind == "door" else "窗-%.0f-%.0f") % (pos, fixed)
    boxes.append({"name": name, "layer": layer, "layer_color": color, "size": size, "location": loc})


def build_plan(segments, columns, openings, wall_height):
    openings = _apply_opening_corrections(list(openings))
    h_walls = [(s["y1"], s.get("thick", WALL_THICKNESS_MM), s["x1"], s["x2"]) for s in segments if s["kind"] == "h"]
    v_walls = [(s["x1"], s.get("thick", WALL_THICKNESS_MM), s["y1"], s["y2"]) for s in segments if s["kind"] == "v"]
    h_walls, v_walls = _merge_walls(h_walls, v_walls)
    attached = _attach_openings(h_walls, v_walls, openings)

    xs = [v for w in h_walls for v in (w[2], w[3])] + [w[0] for w in v_walls]
    ys = [w[0] for w in h_walls] + [v for w in v_walls for v in (w[2], w[3])]
    origin_x, origin_y = min(xs), min(ys)

    boxes = []
    # Opening zones per wall line (for splitting runs and capping extensions).
    h_bounds = {}
    v_bounds = {}
    for op in openings:
        w = op["width_mm"] or 1000.0
        half = w / 2.0
        px, py = op["p1"]
        for y, thick, a, b in h_walls:
            if abs(py - y) <= 300 and (a - half - ATTACH_TOL_MM) <= px <= (b + half + ATTACH_TOL_MM):
                h_bounds.setdefault(round(y, 1), []).append((px - half, px + half))
        for x, thick, a, b in v_walls:
            if abs(px - x) <= 300 and (a - half - ATTACH_TOL_MM) <= py <= (b + half + ATTACH_TOL_MM):
                v_bounds.setdefault(round(x, 1), []).append((py - half, py + half))

    def split_runs(walls, is_h):
        pieces = []
        for fixed, thick, a, b in walls:
            bounds = (h_bounds if is_h else v_bounds).get(round(fixed, 1), [])
            cursor = a
            spans = []
            for oa, ob in sorted(bounds):
                # 只切与该墙段实际重叠的洞口，避免借用同线其他墙段的洞口
                # 生成超出本段范围的“幽灵墙段”。
                if ob < a or oa > b:
                    continue
                if oa > cursor + 50:
                    spans.append((cursor, oa))
                cursor = max(cursor, ob)
                if cursor >= b:
                    break
            if b - cursor > 50:
                spans.append((cursor, b))
            pieces.extend((fixed, thick, pa, pb) for pa, pb in spans if pb - pa >= 100)
        return pieces

    h_pieces = split_runs(h_walls, True)
    v_pieces = split_runs(v_walls, False)
    h_pieces, v_pieces = _extend_junctions(h_pieces, v_pieces, h_bounds, v_bounds)

    for y, thick, pa, pb in h_pieces:
        _emit_wall_box(boxes, True, y, thick, pa, pb, wall_height, origin_x, origin_y)
    for x, thick, pa, pb in v_pieces:
        _emit_wall_box(boxes, False, x, thick, pa, pb, wall_height, origin_x, origin_y)
    for wall, pos, op in attached:
        _emit_opening(boxes, wall[0] == "h", wall[1], wall[2], pos, op, wall_height, origin_x, origin_y)

    for col in columns:
        boxes.append(
            {
                "name": "柱-%.0f-%.0f" % (col["cx_mm"], col["cy_mm"]),
                "layer": LAYER_COLUMN[0],
                "layer_color": LAYER_COLUMN[1],
                "size": (col["dx_mm"] / 1000.0, col["dy_mm"] / 1000.0, col["height_mm"] / 1000.0),
                "location": (
                    (col["cx_mm"] - origin_x) / 1000.0,
                    (col["cy_mm"] - origin_y) / 1000.0,
                    (col["height_mm"] / 1000.0) / 2.0,
                ),
            }
        )
    return boxes, origin_x, origin_y


def _latest_registration() -> dict:
    host_dir = os.path.join(os.environ["LOCALAPPDATA"], "AgentBridge", "hosts")
    matches = sorted(glob.glob(os.path.join(host_dir, "rhino-main-*.json")), key=os.path.getmtime)
    if not matches:
        raise SystemExit("未找到 Rhino host 注册文件，请先启动 AgentBridge Rhino 宿主")
    return json.load(open(matches[-1], encoding="utf-8"))


def _call(base: str, headers: dict, tool: str, args: dict, timeout: int = 60) -> dict:
    body = json.dumps({"arguments": args}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/tools/" + tool, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rollback(base: str, headers: dict, token: str) -> bool:
    body = json.dumps({"rollback_token": token}).encode("utf-8")
    req = urllib.request.Request(base + "/rollback", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return bool(result.get("ok") and result.get("result", {}).get("deleted"))


def _round3(values):
    return tuple(round(float(v), 3) for v in values)


def _same_geo(record, plan_item) -> bool:
    return (
        record.get("layer") == plan_item.get("layer")
        and _round3(record["size"]) == _round3(plan_item["size"])
        and _round3(record["location"]) == _round3(plan_item["location"])
    )


def _load_records(path: str):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8")).get("objects", [])
        except Exception:
            return []
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="天正 DXF → Rhino 墙体建模")
    parser.add_argument("dxf", help="DXF 文件路径")
    parser.add_argument("--dry", action="store_true", help="只解析并输出计划，不调用 Rhino")
    parser.add_argument("--step-delay", type=float, default=0.0, help="每个部件之间的停顿秒数")
    parser.add_argument("--wall-height", type=float, default=3.0, help="墙高（米）")
    parser.add_argument("--update", action="store_true", help="增量更新：只增删改差异")
    parser.add_argument("--union", action="store_true", help="建完后把墙图层布尔合并为一个实体")
    args = parser.parse_args()

    if not os.path.exists(args.dxf):
        raise SystemExit("DXF 文件不存在: %s" % args.dxf)

    doc = ezdxf.readfile(args.dxf)
    has_tch = any(str(entity.dxftype()).startswith("TCH_") for entity in doc.modelspace())
    if has_tch:
        horizontals, vertical_pts = _parse_walls(args.dxf)
        segments = reconstruct_segments(horizontals, vertical_pts)
        openings = _read_openings(args.dxf)
        columns = _read_columns(args.dxf)
        source = "TCH"
    else:
        segments, columns, openings = _parse_t3(doc)
        source = "T3"
    plan, origin_x, origin_y = build_plan(segments, columns, openings, args.wall_height)

    h_count = len([s for s in segments if s["kind"] == "h"])
    v_count = len([s for s in segments if s["kind"] == "v"])
    print("source:", source, "| horizontal walls:", h_count, "| vertical walls:", v_count)
    print("openings:", len(openings), "| columns:", len(columns))
    print("plan boxes:", len(plan))
    print("origin (mm): x %.0f y %.0f" % (origin_x, origin_y))

    if args.dry:
        for item in plan[:10]:
            print("  ", item["name"], item["layer"], item["size"], item["location"])
        return

    reg = _latest_registration()
    base = reg["endpoint"]
    headers = {"x-cadcopilot-token": reg["token"], "Content-Type": "application/json; charset=utf-8"}
    record_path = os.path.join(os.environ["LOCALAPPDATA"], "AgentBridge", "plan-build.json")
    old_records = _load_records(record_path) if args.update else []
    old_by_name = {record["name"]: record for record in old_records}
    new_by_name = {item["name"]: item for item in plan}

    to_create = []
    to_rollback = []
    kept = 0
    for name, item in new_by_name.items():
        old = old_by_name.get(name)
        if old is not None and _same_geo(old, item):
            kept += 1
            continue
        if old is not None:
            to_rollback.append(old)
        to_create.append(item)
    for name, old in old_by_name.items():
        if name not in new_by_name:
            to_rollback.append(old)

    perm = "plan-" + time.strftime("%Y%m%d%H%M%S")
    records = []
    created = 0
    removed = 0
    for record in to_rollback:
        if _rollback(base, headers, record["rollback_token"]):
            removed += 1
    total = len(to_create)
    for index, item in enumerate(to_create, 1):
        res = _call(
            base,
            headers,
            "rhino_create_box",
            {
                "name": item["name"],
                "size": item["size"],
                "location": item["location"],
                "layer": item["layer"],
                "layer_color": item["layer_color"],
                "permission_request_id": perm,
            },
        )
        if not res.get("ok"):
            print("[%d/%d] FAIL %s: %s" % (index, total, item["name"], res.get("error_message")))
            continue
        created += 1
        records.append(
            {
                "name": item["name"],
                "layer": item["layer"],
                "layer_color": item["layer_color"],
                "size": item["size"],
                "location": item["location"],
                "object_id": res["result"]["object_id"],
                "rollback_token": res["rollback_token"],
            }
        )
        if args.step_delay and index < total:
            time.sleep(args.step_delay)

    # Keep unchanged old records.
    for name, old in old_by_name.items():
        if name in new_by_name and _same_geo(old, new_by_name[name]):
            records.append(old)

    summary = _call(base, headers, "rhino_scene_summary", {})
    print(
        "update: created=%d removed=%d kept=%d scene=%s"
        % (created, removed, kept, summary["result"]["object_count"])
    )
    if args.union:
        union_res = _call(
            base,
            headers,
            "rhino_union_layer",
            {"layer": LAYER_WALL[0], "permission_request_id": perm},
            timeout=600,
        )
        print("union:", json.dumps(union_res.get("result"), ensure_ascii=False))
    record = {
        "perm": perm,
        "source": source,
        "objects": sorted(records, key=lambda r: r["name"]),
    }
    with open(record_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    print("records ->", record_path)


if __name__ == "__main__":
    main()
