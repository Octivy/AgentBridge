"""解释层：把软件返回的原始数据翻译成 Agent 容易理解的语义结构。

定位：AgentBridge 只做中间调和方——智能决策归 Agent、执行归软件、连接与
解释归桥。本模块用确定性规则（不调大模型）把快照/场景数据翻译成中文语义，
包括：图纸规模与单位、图层图例（角色解释）、墙体/门窗/柱/楼梯统计、房间
标注、给 Agent 的建议动作等。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 各宿主的现状读取工具（Host Adapter Contract 命名空间）
READ_TOOLS = {
    "autocad": "autocad_get_drawing_snapshot",
    "blender": "blender_scene_summary",
    "rhino": "rhino_scene_summary",
    "sketchup": "sketchup_scene_summary",
}

# 图层名 → 角色解释（确定性规则，覆盖天正常见图层）
_LAYER_ROLES: List[tuple] = [
    ("WALL", "墙体结构"),
    ("COLUMN", "柱"),
    ("WINDOW", "窗"),
    ("DOOR", "门"),
    ("STAIR", "楼梯/台阶"),
    ("DIM", "尺寸标注"),
    ("TEXT", "文字标注"),
    ("DOTE", "轴网"),
    ("EVTR", "立面/标高"),
    ("TITLE", "图框"),
    ("墙", "墙体相关"),
    ("梁", "梁"),
    ("柱", "柱相关"),
    ("幕墙", "幕墙"),
    ("管", "管线"),
    ("房间", "房间标注"),
]


def _layer_role(name: str, semantic_group: str) -> str:
    upper = (name or "").upper()
    for key, role in _LAYER_ROLES:
        if key in upper or key in (name or ""):
            return role
    if semantic_group == "annotation":
        return "标注类"
    if semantic_group == "plan":
        return "平面要素"
    return "其他"


def _first(values: List[Any], default: Any = None) -> Any:
    return values[0] if values else default


def explain_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """解释 AutoCAD 图纸快照（drawing_summary/layers/texts/blocks/entities）。"""

    summary = snapshot.get("drawing_summary") or {}
    bounds = summary.get("bounds") or {}
    min_pt = bounds.get("min") or [0.0, 0.0]
    max_pt = bounds.get("max") or [0.0, 0.0]
    width_mm = float(_first(max_pt, 0.0)) - float(_first(min_pt, 0.0))
    height_mm = float(_first(max_pt[1:], 0.0)) - float(_first(min_pt[1:], 0.0))

    layers = snapshot.get("layers") or []
    legend = [
        {
            "name": layer.get("name"),
            "count": layer.get("count"),
            "types": layer.get("types") or [],
            "semantic_group": layer.get("semantic_group") or "",
            "role": _layer_role(layer.get("name"), layer.get("semantic_group") or ""),
        }
        for layer in layers
    ]

    def count_where(*keywords: str, role_hint: Optional[str] = None) -> int:
        total = 0
        for layer in legend:
            name = str(layer["name"] or "")
            matched = any(keyword in name for keyword in keywords)
            if role_hint:
                matched = matched or role_hint in str(layer["role"])
            if matched:
                total += int(layer["count"] or 0)
        return total

    counts = {
        "walls": count_where("WALL", "墙", role_hint="墙体"),
        "columns": count_where("COLUMN", role_hint="柱"),
        "windows": count_where("WINDOW", role_hint="窗"),
        "doors": count_where("DOOR", role_hint="门"),
        "stairs": count_where("STAIR", role_hint="楼梯"),
        "texts": len(snapshot.get("texts") or []),
        "blocks": sum(int(block.get("insertions") or 0) for block in (snapshot.get("blocks") or [])),
        "entities": int(summary.get("total_entities") or 0),
        "layers": int(summary.get("total_layers") or len(layers)),
    }

    texts = snapshot.get("texts") or []
    room_labels = [text.get("content") for text in texts if text.get("content") and str(text.get("content")).strip()][:12]

    frames = snapshot.get("frames") or []
    dominant = frames[0].get("dominant_layers") if frames else []

    suggestions = []
    if counts["walls"]:
        suggestions.append(f"WALL 层含 {counts['walls']} 条墙线：可提取双线墙中心线生成墙体（厚度取双线间距）")
    if counts["windows"]:
        suggestions.append(f"WINDOW 层 {counts['windows']} 个窗：窗宽=窗线长度，可在墙体上开洞")
    if counts["doors"]:
        suggestions.append(f"门 {counts['doors']} 个：门宽=块比例，门扇方向=块旋转角，可开洞")
    if room_labels:
        suggestions.append(f"房间标注：{'、'.join(str(label) for label in room_labels[:6])}")
    suggestions.append("写操作流程：dry-run 预览 → 拿 permission_token/preview_hash → 提交；可回滚")

    return {
        "source": "autocad_snapshot",
        "units": summary.get("units") or "Unknown",
        "size": {
            "width_mm": round(width_mm, 1),
            "height_mm": round(height_mm, 1),
            "width_m": round(width_mm / 1000.0, 2),
            "height_m": round(height_mm / 1000.0, 2),
        },
        "frames": int(summary.get("detected_frames") or 0),
        "counts": counts,
        "layer_legend": legend,
        "dominant_layers": dominant,
        "room_labels": room_labels,
        "suggestions": suggestions,
    }


def explain_scene(host_kind: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """解释建模软件的场景摘要（object_count/layers）。"""

    layers = data.get("layers") or []
    suggestions = []
    if layers:
        suggestions.append(f"场景包含 {len(layers)} 个图层：{', '.join(str(layer) for layer in layers[:8])}")
    suggestions.append("创建几何：dry-run 预览 → 提交；rollback_token 可整批回滚")
    return {
        "source": f"{host_kind}_scene",
        "document": data.get("document") or "",
        "object_count": data.get("object_count"),
        "layers": layers,
        "suggestions": suggestions,
    }


def explain_tool_result(host_kind: str, tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """把某宿主读取工具的结果翻译成语义解释（snapshot → explain_snapshot）。"""

    data = tool_result.get("data") if isinstance(tool_result, dict) else None
    if host_kind == "autocad" and isinstance(data, dict) and data.get("snapshot"):
        return explain_snapshot(data["snapshot"])
    if isinstance(data, dict):
        return explain_scene(host_kind, data)
    return {"source": host_kind, "note": "no readable data in tool result"}


__all__ = ["READ_TOOLS", "explain_snapshot", "explain_scene", "explain_tool_result"]
