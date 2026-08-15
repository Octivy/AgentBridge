"""AgentBridge 宿主工具总览：列出各宿主可用的写工具与参数要求。"""

import json
import os
import urllib.request
from pathlib import Path

registry = Path(os.environ["LOCALAPPDATA"]) / "AgentBridge" / "hosts"
for path in sorted(registry.glob("*.json")):
    reg = json.loads(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(
        reg["endpoint"].rstrip("/") + "/manifest",
        headers={"x-cadcopilot-token": reg["token"]},
    )
    try:
        manifest = json.loads(urllib.request.urlopen(req, timeout=5).read())
    except Exception as exc:
        print("==", reg["host_id"], "FAIL", exc)
        continue
    tools = [t["tool_name"] for t in manifest.get("tools", [])]
    print("==", reg["host_id"], "(" + reg["host_kind"] + ")", "tools=", tools)
    for tool in manifest.get("tools", []):
        side = str(tool.get("side_effect_level") or "none")
        if side == "none":
            continue
        required = (tool.get("input_schema") or {}).get("required", [])
        print("   WRITE", tool["tool_name"], "required=", required)
