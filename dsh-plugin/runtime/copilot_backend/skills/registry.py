import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class SkillToolCallTemplate:
    tool_name: str
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SkillParameterDefinition:
    name: str
    label: str
    value_type: str = "string"
    required: bool = True
    default_value: str = ""
    options: List[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class SkillAcceptanceExample:
    title: str
    user_message: str
    expected_behavior: str
    manual_test: bool = False


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    name: str
    description: str
    category: str
    mcp_tools: List[str] = field(default_factory=list)
    auto_tool_calls: List[SkillToolCallTemplate] = field(default_factory=list)
    parameters: List[SkillParameterDefinition] = field(default_factory=list)
    planner_hints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    acceptance_examples: List[SkillAcceptanceExample] = field(default_factory=list)
    enabled: bool = True


_SKILLS: List[SkillDefinition] = [
    SkillDefinition(
        skill_id="drawing_snapshot_analysis",
        name="图纸理解",
        description="读取当前图纸、图层、实体、块、文字和未知对象，为 AI 建立可验证上下文。",
        category="analysis",
        mcp_tools=["get_drawing_snapshot", "list_layers", "arch_get_drawing_context"],
        auto_tool_calls=[SkillToolCallTemplate("get_drawing_snapshot")],
        planner_hints=["任何识别或修改任务都应先读取当前图纸，不得根据用户描述猜测图面。"],
        examples=["分析当前图纸的图层、图块、对象类型和异常项"],
        acceptance_examples=[
            SkillAcceptanceExample(
                title="只读图纸分析",
                user_message="先分析这张图",
                expected_behavior="先读取快照并生成图纸理解上下文，不触发写入。",
            )
        ],
    ),
    SkillDefinition(
        skill_id="functional_object_recognition",
        name="功能对象识别",
        description="把图层线、普通/动态块、自定义对象和代理对象统一识别为墙、门、窗或未知。",
        category="recognition",
        mcp_tools=["arch_recognize_functional_objects"],
        planner_hints=["输出识别证据、置信度和支持状态；unsupported 对象不得由模型补猜。"],
        examples=["识别选定范围中的墙、门、窗和未知对象"],
        acceptance_examples=[
            SkillAcceptanceExample(
                title="跨表达识别",
                user_message="识别图里的墙门窗",
                expected_behavior="读取快照后返回统一功能对象及其来源证据。",
            )
        ],
    ),
    SkillDefinition(
        skill_id="outer_outline_drawing",
        name="绘制外围轮廓",
        description="提取整平面最外闭合轮廓，预演后绘制一条普通闭合多段线。",
        category="conversion",
        mcp_tools=["arch_extract_outer_outline", "arch_draw_outer_outline"],
        planner_hints=["只承诺外围轮廓；真实写入前必须预演并取得用户授权。"],
        examples=["把当前平面的外围轮廓画到 AI-OUTLINE 图层"],
        acceptance_examples=[
            SkillAcceptanceExample(
                title="外围轮廓预演",
                user_message="绘制这层平面的外围轮廓",
                expected_behavior="先提取，再预演，确认后只写入一条闭合多段线。",
            )
        ],
    ),
    SkillDefinition(
        skill_id="layer_normalization",
        name="统一图层",
        description="生成保守图层映射建议，并在用户确认后迁移当前空间中的实体。",
        category="organization",
        mcp_tools=["arch_suggest_layer_mapping", "arch_apply_layer_mapping"],
        parameters=[
            SkillParameterDefinition(
                name="mapping",
                label="图层映射",
                value_type="object",
                required=False,
                description="源图层到目标图层的已确认映射。",
            )
        ],
        planner_hints=["未知图层不自动猜测；批量迁移必须预演、确认、复验并支持回滚。"],
        examples=["把墙、门、窗图层统一为 A-WALL、A-DOOR、A-WIND"],
        acceptance_examples=[
            SkillAcceptanceExample(
                title="图层映射确认",
                user_message="统一这张图的图层",
                expected_behavior="先生成建议，等待确认后再迁移实体。",
                manual_test=True,
            )
        ],
    ),
]


def list_skills(*, enabled_only: bool = False) -> List[SkillDefinition]:
    return list(_SKILLS)


def get_skill(skill_id: str) -> Optional[SkillDefinition]:
    normalized = (skill_id or "").strip()
    return next((skill for skill in _SKILLS if skill.skill_id == normalized), None)


def get_enabled_skill(skill_id: str) -> Optional[SkillDefinition]:
    skill = get_skill(skill_id)
    return skill if skill and skill.enabled else None


def expand_skills_to_tool_calls(skill_ids: List[str]) -> List[SkillToolCallTemplate]:
    expanded: List[SkillToolCallTemplate] = []
    seen = set()
    for skill_id in skill_ids:
        skill = get_enabled_skill(skill_id)
        if skill is None:
            continue
        for tool_call in skill.auto_tool_calls:
            key = json.dumps(
                {"tool_name": tool_call.tool_name, "arguments": tool_call.arguments},
                ensure_ascii=False,
                sort_keys=True,
            )
            if key not in seen:
                seen.add(key)
                expanded.append(tool_call)
    return expanded
