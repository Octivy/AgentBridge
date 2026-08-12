from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from cadmcp.result_protocol import STANDARD_TOOL_RESULT_SCHEMA


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    display_name: str
    category: str
    description: str
    input_schema: dict
    dry_run_supported: bool
    side_effect_level: str
    result_schema: dict
    risk_level: str = ""
    transaction_required: Optional[bool] = None
    rollback_supported: bool = False
    permission_scope: str = "session"
    collapse_policy: str = ""
    ui_preview_kind: str = ""
    audit_required: bool = True

    def __post_init__(self) -> None:
        side_effect = (self.side_effect_level or "none").strip().lower()
        risk_level = (self.risk_level or "").strip().lower()
        if not risk_level:
            risk_level = "read_only" if side_effect == "none" else "reversible_write"
            object.__setattr__(self, "risk_level", risk_level)
        if self.transaction_required is None:
            object.__setattr__(self, "transaction_required", risk_level != "read_only")
        if not self.collapse_policy:
            object.__setattr__(
                self,
                "collapse_policy",
                "collapse_read" if risk_level == "read_only" else "expanded_on_write",
            )
        if not self.ui_preview_kind:
            object.__setattr__(
                self,
                "ui_preview_kind",
                "cad_diff" if self.dry_run_supported and risk_level != "read_only" else "none",
            )


def _read_tool(
    name: str,
    display_name: str,
    category: str,
    description: str,
    properties: dict | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        tool_name=name,
        display_name=display_name,
        category=category,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties or {},
            "additionalProperties": False,
        },
        dry_run_supported=False,
        side_effect_level="none",
        result_schema=STANDARD_TOOL_RESULT_SCHEMA,
    )


def _write_tool(
    name: str,
    display_name: str,
    category: str,
    description: str,
    properties: dict,
    required: list[str] | None = None,
    *,
    rollback_supported: bool = True,
    risk_level: str = "reversible_write",
) -> ToolDefinition:
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return ToolDefinition(
        tool_name=name,
        display_name=display_name,
        category=category,
        description=description,
        input_schema=schema,
        dry_run_supported=True,
        side_effect_level="high",
        risk_level=risk_level,
        rollback_supported=rollback_supported,
        result_schema=STANDARD_TOOL_RESULT_SCHEMA,
    )


_POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3}


_TOOLS: List[ToolDefinition] = [
    _read_tool("cad_health_check", "CAD 健康检查", "system", "检查 AutoCAD 本地桥、活动图纸和插件版本。"),
    _read_tool(
        "get_drawing_snapshot",
        "读取图纸快照",
        "analysis",
        "读取当前图纸的图层、实体、文字、块、自定义对象和代理对象摘要。",
        {"scope": {"type": "object"}},
    ),
    _read_tool("list_layers", "读取图层", "analysis", "读取当前图纸的图层状态和实体统计。"),
    _write_tool(
        "ensure_layer",
        "确保图层存在",
        "organization",
        "预演并创建或更新一个普通 CAD 图层。",
        {
            "layer": {"type": "string"},
            "layer_name": {"type": "string"},
            "color": {"type": "integer", "minimum": 1, "maximum": 255},
        },
        rollback_supported=False,
    ),
    _write_tool(
        "draw_line",
        "绘制直线",
        "drawing",
        "预演并绘制一条普通 CAD 直线。",
        {"start": _POINT, "end": _POINT, "layer": {"type": "string"}},
        ["start", "end"],
    ),
    _write_tool(
        "execute_draw_batch",
        "执行绘图批次",
        "drawing",
        "预演并在一个事务中执行经过验证的普通 CAD 绘图命令。",
        {"commands": {"type": "array", "items": {"type": "object"}, "minItems": 1}},
        ["commands"],
    ),
    _write_tool(
        "cad_rollback_transaction",
        "回滚 CAD 事务",
        "safety",
        "回滚由本插件提交且尚未被用户继续修改的 CAD 实体变更。",
        {"rollback_token": {"type": "string"}},
        ["rollback_token"],
        rollback_supported=False,
        risk_level="destructive_write",
    ),
    _read_tool(
        "arch_get_drawing_context",
        "图纸理解",
        "analysis",
        "把当前快照整理为模型可使用的图层、实体、块、文字、范围和诊断上下文。",
        {
            "drawing_id": {"type": "string"},
            "units": {"type": "string"},
            "snapshot": {"type": "object"},
        },
    ),
    _read_tool(
        "arch_recognize_functional_objects",
        "识别功能对象",
        "recognition",
        "把图层线、块、自定义对象和代理对象统一识别为墙、门、窗或未知对象。",
        {
            "drawing_id": {"type": "string"},
            "snapshot": {"type": "object"},
            "scope": {"type": "object"},
            "wall_layers": {"type": "array", "items": {"type": "string"}},
            "door_layers": {"type": "array", "items": {"type": "string"}},
            "window_layers": {"type": "array", "items": {"type": "string"}},
        },
    ),
    _read_tool(
        "arch_extract_outer_outline",
        "提取外围轮廓",
        "conversion",
        "从选定范围的单线或多段线提取整平面最外闭合轮廓和面积。",
        {
            "drawing_id": {"type": "string"},
            "units": {"type": "string"},
            "snapshot": {"type": "object"},
            "scope": {"type": "object"},
            "source_layers": {"type": "array", "items": {"type": "string"}},
            "tolerance": {"type": "number", "exclusiveMinimum": 0},
        },
    ),
    _write_tool(
        "arch_draw_outer_outline",
        "绘制外围轮廓",
        "conversion",
        "预演并把已确认的外围轮廓绘制为独立图层上的一条闭合多段线。",
        {
            "outline": {"type": "object"},
            "boundary": {"type": "array", "items": _POINT, "minItems": 3},
            "layer": {"type": "string"},
            "object_id": {"type": "string"},
        },
    ),
    _read_tool(
        "arch_suggest_layer_mapping",
        "生成图层映射建议",
        "organization",
        "根据快照生成保守图层映射建议，未知图层保持未映射。",
        {
            "drawing_id": {"type": "string"},
            "snapshot": {"type": "object"},
            "target_layers": {"type": "object"},
        },
    ),
    _write_tool(
        "arch_apply_layer_mapping",
        "应用图层映射",
        "organization",
        "预演并迁移当前空间中命中映射的实体，可用 Handle 进一步限定。",
        {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_layer": {"type": "string"},
                        "target_layer": {"type": "string"},
                        "target_color": {"type": "integer", "minimum": 1, "maximum": 255},
                        "semantic_type": {"type": "string"},
                        "entity_count": {"type": "integer", "minimum": 0},
                    },
                    "required": ["source_layer", "target_layer"],
                    "additionalProperties": True,
                },
                "minItems": 1,
            },
            "entity_handles": {"type": "array", "items": {"type": "string"}},
        },
        ["mappings"],
    ),
]


PRODUCT_MVP_TOOL_NAMES = frozenset(tool.tool_name for tool in _TOOLS)


def list_tools() -> List[ToolDefinition]:
    return list(_TOOLS)


def get_tool(tool_name: str) -> Optional[ToolDefinition]:
    normalized = (tool_name or "").strip()
    return next((tool for tool in _TOOLS if tool.tool_name == normalized), None)


def list_product_tools() -> List[ToolDefinition]:
    return list_tools()


def get_product_tool(tool_name: str) -> Optional[ToolDefinition]:
    return get_tool(tool_name)
