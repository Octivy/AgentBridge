"""Agent-driven whole-floor build: region by region, check after each region.

The plan (DXF -> components) is only the *data*; creation, verification and
fixing are driven through the live Rhino tools (create/get/delete), one region
at a time, with audits between regions.
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, r"H:\codex\AgentBridge\copilot_backend\scripts")
import dxf_to_rhino_plan as p  # noqa: E402
import _debug_gap_audit as audit  # noqa: E402

STEP_DELAY = 0.25


def live_host():
    host_dir = os.path.join(os.environ["LOCALAPPDATA"], "AgentBridge", "hosts")
    live = []
    for name in os.listdir(host_dir):
        if not name.startswith("rhino-main-"):
            continue
        with open(os.path.join(host_dir, name), encoding="utf-8") as fh:
            c = json.load(fh)
        if not c.get("pid") or not c.get("endpoint"):
            continue
        try:
            req = urllib.request.Request(c["endpoint"] + "/health", headers={"x-cadcopilot-token": c.get("token", "")})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    live.append(c)
        except Exception:
            continue
    if not live:
        raise SystemExit("no live Rhino host")
    return max(live, key=lambda c: c.get("registered_at") or "")


REG = live_host()


def call(method, path, payload=None, timeout=300):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(REG["endpoint"] + path, data=data, headers={
        "x-cadcopilot-token": REG["token"], "Content-Type": "application/json; charset=utf-8"}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_box(name, size, loc, layer, layer_color):
    perm = "perm-floor-" + str(int(time.time() * 1000))
    r = call("POST", "/tools/rhino_create_box", {"arguments": {
        "name": name, "size": size, "location": loc,
        "layer": layer, "layer_color": layer_color,
        "permission_request_id": perm,
    }})
    if not r.get("ok"):
        raise RuntimeError("create failed %s: %s" % (name, r.get("error_message")))
    return r["result"]["object_id"]


def delete_object(object_id):
    perm = "perm-floor-" + str(int(time.time() * 1000))
    return call("POST", "/tools/rhino_delete_object", {"arguments": {
        "object_id": object_id, "permission_request_id": perm,
    }})


def live_boxes():
    g = call("POST", "/tools/rhino_get_objects", {"arguments": {"limit": 5000}})
    out = []
    for o in g["result"]["objects"]:
        b = o.get("bbox")
        if not b:
            continue
        out.append({
            "id": o["id"], "name": o.get("name"), "layer": o["layer"], "bbox": b,
            "size": [b[3] - b[0], b[4] - b[1], b[5] - b[2]],
            "location": [(b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, (b[2] + b[5]) / 2.0],
        })
    return out


def to_audit_boxes(boxes, x0=None, y0=None, x1=None, y1=None):
    out = []
    for b in boxes:
        bb = b["bbox"]
        if x0 is not None and (bb[3] < x0 or bb[0] > x1 or bb[4] < y0 or bb[1] > y1):
            continue
        out.append({
            "name": b["name"] or b["id"], "layer": b["layer"], "size": b["size"],
            "x0": bb[0] * 1000.0, "y0": bb[1] * 1000.0, "x1": bb[3] * 1000.0, "y1": bb[4] * 1000.0,
            "z": bb[5] * 1000.0,
        })
    return out


def audit_boxes(audit_boxes):
    bad = audit.opening_intrusions(audit_boxes)
    gaps = audit.junction_gaps([{"name": b["name"], "x0": b["x0"], "y0": b["y0"], "x1": b["x1"], "y1": b["y1"]}
                                for b in audit_boxes if b["layer"] == "墙"])
    return bad, gaps


print("== 0. 清理现场 ==")
for b in live_boxes():
    delete_object(b["id"])
time.sleep(0.5)
print("   剩余:", len(live_boxes()))

print("== 1. 读取图纸数据 ==")
dxf = r"H:\codex\AgentBridge\Tsetfile\一层平面图_t3门墙柱.dxf"
doc = p.ezdxf.readfile(dxf)
segments, columns, openings = p._parse_t3(doc)
plan, ox, oy = p.build_plan(segments, columns, openings, 3.0)
print("   构件总数:", len(plan))

LAYER_ORDER = {"墙": 0, "柱": 1, "楣": 2, "台": 2, "门": 3, "窗": 3}
pieces = []
for b in plan:
    x0, y0, x1, y1, _ = audit.box_abs(b, ox, oy)
    pieces.append((b, x0, y0, x1, y1))

# 按 5m 横向分区（相对模型原点），区内按 墙->柱->楣/台->门/窗 排序
regions = {}
for b, x0, y0, x1, y1 in pieces:
    band = int(((x0 + x1) / 2.0 - ox) // 5000)
    regions.setdefault(band, []).append((b, x0, y0, x1, y1))
for band in regions:
    regions[band].sort(key=lambda item: (LAYER_ORDER.get(item[0]["name"].split("-")[0], 9), item[0]["name"]))

built = 0
for band in sorted(regions):
    items = regions[band]
    rx0 = min(i[1] for i in items) - 1500.0
    ry0 = min(i[2] for i in items) - 1500.0
    rx1 = max(i[3] for i in items) + 1500.0
    ry1 = max(i[4] for i in items) + 1500.0
    print("== 区 %2d: %3d 个构件 (x %.1f..%.1fm, y %.1f..%.1fm) ==" % (
        band, len(items), rx0 / 1000.0, rx1 / 1000.0, ry0 / 1000.0, ry1 / 1000.0))
    for b, x0, y0, x1, y1 in items:
        oid = create_box(
            b["name"],
            [(x1 - x0) / 1000.0, (y1 - y0) / 1000.0, b["size"][2]],
            [((x0 + x1) / 2.0 - ox) / 1000.0, ((y0 + y1) / 2.0 - oy) / 1000.0, b["location"][2]],
            b["layer"], b["layer_color"],
        )
        built += 1
        time.sleep(STEP_DELAY)
    time.sleep(0.4)
    bad, gaps = audit_boxes(to_audit_boxes(live_boxes(), rx0, ry0, rx1, ry1))
    print("   检查: 净空侵入 %d, 交接缝隙 %d %s" % (len(bad), len(gaps), "FAIL" if bad or gaps else "OK"))
    for row in bad[:5]:
        print("     侵入:", row)
    for row in gaps[:5]:
        print("     缝隙:", row)
    if bad or gaps:
        raise SystemExit("区域 %d 检查未通过，停止（避免带着错误继续建）" % band)

print("== 终审: 整层 ==")
time.sleep(0.5)
all_boxes = live_boxes()
bad, gaps = audit_boxes(to_audit_boxes(all_boxes))
print("   对象总数:", len(all_boxes), "| 净空侵入:", len(bad), "| 交接缝隙:", len(gaps))
from collections import Counter
print("   分层:", dict(Counter(b["layer"] for b in all_boxes)))
print("   有名字对象:", sum(1 for b in all_boxes if b["name"]))

# 数据一致性：按名字核对实际位置与图纸数据是否一致（抓转置/错位）
expected = {}
for b, x0, y0, x1, y1 in pieces:
    expected[b["name"]] = ((x0 - ox) / 1000.0, (y0 - oy) / 1000.0, (x1 - ox) / 1000.0, (y1 - oy) / 1000.0)
mismatch = []
for b in all_boxes:
    if b["name"] not in expected:
        mismatch.append((b["name"], "不在图纸数据中"))
        continue
    ex = expected[b["name"]]
    bb = b["bbox"]
    tol = 0.06
    if (abs(bb[0] - ex[0]) > tol or abs(bb[1] - ex[1]) > tol
            or abs(bb[3] - ex[2]) > tol or abs(bb[4] - ex[3]) > tol):
        mismatch.append((b["name"], "位置偏差: %s vs 期望 %s" % ([round(v, 2) for v in bb[:4]], [round(v, 2) for v in ex])))
print("   数据一致性: %d 处不匹配" % len(mismatch))
for row in mismatch[:10]:
    print("     ", row)
if bad or gaps:
    for row in bad[:10]:
        print("   侵入:", row)
    for row in gaps[:10]:
        print("   缝隙:", row)
    raise SystemExit("终审未通过")
if mismatch:
    raise SystemExit("数据一致性未通过")
print("   终审通过 OK")
