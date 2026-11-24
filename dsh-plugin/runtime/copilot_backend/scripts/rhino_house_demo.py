"""AgentBridge Rhino 逐步建房演示（需先启动 Rhino host）。

用法：
    python rhino_house_demo.py [--step-delay 2.5] [--dry]

通过 AgentBridge Rhino 宿主在 Rhino 中逐部件创建一栋小房子，
每步停顿 ``--step-delay`` 秒，方便在 Rhino 界面看到部件依次出现。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import time
import urllib.request


PARTS = [
    ("地板", [10.0, 8.0, 0.4], [0.0, 0.0, 0.2], "地面"),
    ("前墙左", [4.2, 0.3, 3.0], [-2.9, -3.85, 1.5], "墙体"),
    ("前墙右", [4.2, 0.3, 3.0], [2.9, -3.85, 1.5], "墙体"),
    ("门楣", [1.6, 0.3, 1.0], [0.0, -3.85, 2.5], "墙体"),
    ("后墙", [10.0, 0.3, 3.0], [0.0, 3.85, 1.5], "墙体"),
    ("左墙", [0.3, 7.4, 3.0], [-4.85, 0.0, 1.5], "墙体"),
    ("右墙", [0.3, 7.4, 3.0], [4.85, 0.0, 1.5], "墙体"),
    ("屋顶", [10.8, 8.8, 0.35], [0.0, 0.0, 3.175], "屋顶"),
    ("门", [1.4, 0.25, 2.0], [0.0, -3.65, 1.0], "门窗"),
    ("窗左", [1.2, 0.25, 1.2], [-2.9, -3.65, 1.8], "门窗"),
    ("窗右", [1.2, 0.25, 1.2], [2.9, -3.65, 1.8], "门窗"),
]


def _latest_registration() -> dict:
    host_dir = os.path.join(os.environ["LOCALAPPDATA"], "AgentBridge", "hosts")
    matches = sorted(glob.glob(os.path.join(host_dir, "rhino-main-*.json")), key=os.path.getmtime)
    if not matches:
        raise SystemExit("未找到 Rhino host 注册文件，请先启动 AgentBridge Rhino 宿主")
    return json.load(open(matches[-1], encoding="utf-8"))


def _call(base: str, headers: dict, tool: str, args: dict, timeout: int = 30) -> dict:
    body = json.dumps({"arguments": args}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/tools/" + tool, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentBridge Rhino 逐步建房演示")
    parser.add_argument("--step-delay", type=float, default=2.5, help="每步停顿秒数")
    parser.add_argument("--dry", action="store_true", help="只打印计划，不调用 Rhino")
    args = parser.parse_args()

    reg = _latest_registration()
    base = reg["endpoint"]
    headers = {"x-cadcopilot-token": reg["token"], "Content-Type": "application/json; charset=utf-8"}
    perm = "house-" + time.strftime("%Y%m%d%H%M%S")
    print("host:", base, "| step-delay:", args.step_delay, "s")

    if not args.dry:
        summary = _call(base, headers, "rhino_scene_summary", {})
        print("scene before:", summary["result"]["object_count"], "objects")

    created = []
    total = len(PARTS)
    for index, (name, size, loc, _kind) in enumerate(PARTS, 1):
        print("[%d/%d] 放置：%s  size=%s" % (index, total, name, size), flush=True)
        if args.dry:
            continue
        res = _call(
            base,
            headers,
            "rhino_create_box",
            {"name": name, "size": size, "location": loc, "permission_request_id": perm},
        )
        if not res.get("ok"):
            print("  失败：%s" % res.get("error_message"))
            continue
        created.append((name, res["rollback_token"]))
        print("  已创建 id=%s" % res["result"]["object_id"], flush=True)
        if index < total:
            time.sleep(max(0.0, float(args.step_delay)))

    if args.dry:
        return

    summary = _call(base, headers, "rhino_scene_summary", {})
    print("scene after:", summary["result"]["object_count"], "objects")
    record = {"perm": perm, "created": created}
    out = os.path.join(os.environ["LOCALAPPDATA"], "AgentBridge", "house-build.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    print("tokens ->", out)


if __name__ == "__main__":
    main()
