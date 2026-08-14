"""Agent loop demo: inspect -> build -> check -> modify -> recheck.

Coordinates: a real door/window region is read from the T3 DXF, shifted to the
origin for visibility in a fresh Rhino document.
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, r"H:\codex\AgentBridge\copilot_backend\scripts")
import dxf_to_rhino_plan as p  # noqa: E402
import _debug_gap_audit as audit  # noqa: E402


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


def call(method, path, payload=None, timeout=120):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(REG["endpoint"] + path, data=data, headers={
        "x-cadcopilot-token": REG["token"], "Content-Type": "application/json; charset=utf-8"}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_box(name, size, loc, layer, layer_color):
    perm = "perm-loop-" + str(int(time.time() * 1000))
    r = call("POST", "/tools/rhino_create_box", {"arguments": {
        "name": name, "size": size, "location": loc,
        "layer": layer, "layer_color": layer_color,
        "permission_request_id": perm,
    }})
    if not r.get("ok"):
        raise RuntimeError("create failed: %s" % r.get("error_message"))
    return r["result"]["object_id"]


def delete_object(object_id):
    perm = "perm-loop-" + str(int(time.time() * 1000))
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
            "id": o["id"], "name": o.get("name"), "layer": o["layer"],
            "bbox": b,
            "size": [b[3] - b[0], b[4] - b[1], b[5] - b[2]],
            "location": [(b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, (b[2] + b[5]) / 2.0],
        })
    return out


def audit_live(boxes, scale=1000.0):
    audit_boxes = []
    for b in boxes:
        audit_boxes.append({
            "name": b["name"] or b["id"], "layer": b["layer"], "size": b["size"],
            "x0": b["bbox"][0] * scale, "y0": b["bbox"][1] * scale,
            "x1": b["bbox"][3] * scale, "y1": b["bbox"][4] * scale,
            "z": b["bbox"][5] * scale,
        })
    bad = audit.opening_intrusions(audit_boxes)
    gaps = audit.junction_gaps([{"name": b["name"], "x0": b["x0"], "y0": b["y0"], "x1": b["x1"], "y1": b["y1"]}
                                for b in audit_boxes if b["layer"] == "墙"])
    return bad, gaps


print("== 步骤0: 清理现场（删除所有遗留测试对象） ==")
for b in live_boxes():
    r = delete_object(b["id"])
    print("   delete %s -> %s" % (b["name"] or b["id"], r.get("ok")))
time.sleep(0.5)
print("   剩余对象:", len(live_boxes()))

print("== 步骤1: 验证基础设施（命名 + 删除） ==")
oid = create_box("LOOP-INFRA", [0.5, 0.5, 0.5], [0, 0, 0.25], "测试", "00FF00")
time.sleep(0.3)
infra = [b for b in live_boxes() if b["id"] == oid][0]
print("   命名生效:", infra.get("name") == "LOOP-INFRA", "| 图层:", infra["layer"])
r = delete_object(oid)
print("   删除生效:", r.get("ok"), r.get("result", {}).get("deleted"))

print("== 步骤2: 读取图纸数据（真实窗洞区域，平移到原点） ==")
dxf = r"H:\codex\AgentBridge\Tsetfile\一层平面图_t3门墙柱.dxf"
doc = p.ezdxf.readfile(dxf)
segments, columns, openings = p._parse_t3(doc)
plan, ox, oy = p.build_plan(segments, columns, openings, 3.0)

SHIFT_X = 40660000.0
SHIFT_Y = 3308600.0
pieces = []
for b in plan:
    x0, y0, x1, y1, _ = audit.box_abs(b, ox, oy)
    if x1 > 40661000 and x0 < 40670000 and y1 > 3308900 and y0 < 3309900:
        pieces.append((b, (x0 - SHIFT_X) / 1000.0, (y0 - SHIFT_Y) / 1000.0, (x1 - SHIFT_X) / 1000.0, (y1 - SHIFT_Y) / 1000.0))
print("   读取到 %d 个构件:" % len(pieces))
for b, x0, y0, x1, y1 in pieces:
    print("     %-6s %-28s x=%.2f..%.2f y=%.2f..%.2f" % (b["layer"], b["name"], x0, x1, y0, y1))

print("== 步骤3: 建模（逐个创建，0.8s 间隔便于观察） ==")
created = []
for b, x0, y0, x1, y1 in pieces:
    sx, sy = x1 - x0, y1 - y0
    oid = create_box(
        b["name"], [sx, sy, b["size"][2]],
        [(x0 + x1) / 2.0, (y0 + y1) / 2.0, b["location"][2]],
        b["layer"], b["layer_color"],
    )
    created.append((b["name"], oid))
    print("     created %-28s -> %s" % (b["name"], oid))
    time.sleep(0.8)

print("== 步骤4: 检查（交接缝隙 + 门/窗净空侵入） ==")
time.sleep(0.5)
bad, gaps = audit_live(live_boxes())
print("   满高墙侵入门/窗净空:", len(bad), "| 垂直交接缝隙:", len(gaps))

print("== 步骤5: 模拟坏数据——在窗洞正中间加一道满高墙 ==")
time.sleep(0.5)
bad_oid = create_box("墙-H-BAD-跨窗洞", [1.0, 0.2, 3.0], [3.3, 0.636, 1.5], "墙", "C9C9C9")
time.sleep(0.5)
bad, gaps = audit_live(live_boxes())
print("   检查发现 %d 处墙穿门窗净空:" % len(bad))
for row in bad[:5]:
    print("     ", row)

print("== 步骤6: 修改（按对象 ID 删除问题墙） ==")
r = delete_object(bad_oid)
print("   删除:", r.get("ok"), r.get("result", {}).get("deleted"))
time.sleep(0.5)

print("== 步骤7: 再检查 ==")
bad, gaps = audit_live(live_boxes())
print("   满高墙侵入门/窗净空:", len(bad), "| 垂直交接缝隙:", len(gaps))
print("   场景对象（带名字）:")
for b in live_boxes():
    print("     %-6s %-30s id=%s" % (b["layer"], b.get("name"), b["id"]))
