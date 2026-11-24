import uuid

from gateway.service import gateway_model_service
from knowledge.service import knowledge_query_service
from shared.schemas import ChatMessageRequest, ChatMessageResponse, KnowledgeQueryRequest


STANDARD_CHAT_SYSTEM_PROMPT = """你是 AgentBridge 的标准模式助手。

能力边界：
1. 可以回答建筑设计、建筑规范理解、CAD 使用、图纸审查、工程管理、软件使用和通用知识问题。
2. 不要把标准模式限制为 DWG 图纸操作；如果用户问题与当前图纸无关，也应正常回答。
3. 如果问题涉及现行法规、建筑设计规范、防火规范、地方标准、收费政策、软件版本等可能变化的信息，请明确提示“需要以官方现行文本/最新发布版本为准”。在你无法联网核验时，不要声称这是最新版本。
4. 标准模式默认不直接写入或修改 CAD 图纸。涉及多步骤绘图、批量修改、图层整理等任务时，建议用户切换到智能体模式。
5. 回答要直接、结构清楚；如果引用规范条文，优先说明适用范围、关键限制和需要复核的条件。
"""


async def handle_standard_chat(request: ChatMessageRequest) -> ChatMessageResponse:
    trace_id = (request.trace_id or "").strip() or str(uuid.uuid4())
    request.trace_id = trace_id
    knowledge_mode = (request.knowledge_mode or "auto").strip().lower()
    if knowledge_mode != "off" and knowledge_query_service.configured:
        knowledge = await knowledge_query_service.query(
            KnowledgeQueryRequest(
                question=request.message,
                provider=request.provider,
                model=request.model,
                api_key=request.api_key,
                api_base_url=request.api_base_url,
                protocol=request.protocol,
                capabilities=request.capabilities,
                trace_id=trace_id,
            )
        )
        if knowledge.citations or knowledge_mode == "required" or _looks_like_standard_query(request.message):
            return ChatMessageResponse(
                reply_text=knowledge.answer or knowledge.warning,
                commands=[],
                trace_id=trace_id,
                model_provider=knowledge.model_provider,
                model_name=knowledge.model_name,
                knowledge_grounded=knowledge.grounded,
                knowledge_citations=knowledge.citations,
                knowledge_warning=knowledge.warning,
            )
    result = await gateway_model_service.request_text_result(request, STANDARD_CHAT_SYSTEM_PROMPT)
    return ChatMessageResponse(
        reply_text=result.text,
        commands=[],
        legacy_fallback_used=False,
        trace_id=trace_id,
        model_provider=result.provider,
        model_name=result.model,
    )


def _looks_like_standard_query(value: str) -> bool:
    text = value or ""
    return any(keyword in text for keyword in ("规范", "标准", "条文", "法规", "防火", "面积规则", "技术规则"))
