from planner.api import planner_agent_service
from shared.schemas import ChatMessageRequest, ChatMessageResponse


async def handle_agent_draw(request: ChatMessageRequest) -> ChatMessageResponse:
    return await planner_agent_service.run_draw_request(request)