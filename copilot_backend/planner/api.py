from typing import Protocol, Optional

from planner.agent_service import PlannerAgentService
from planner.persistent_store import JsonPlannerStore
from shared.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    PlannerTaskDetailResponse,
    PlannerTaskPermissionDecisionRequest,
    PlannerTaskResumeRequest,
    PlannerTaskSummaryResponse,
)
from shared.settings import CADCOPILOT_PLANNER_STORE_PATH


class PlannerApplicationService(Protocol):
    async def run_draw_request(self, request: ChatMessageRequest) -> ChatMessageResponse: ...

    def list_recent_tasks(self, limit: int = 10, status_filter: Optional[str] = None) -> list[PlannerTaskSummaryResponse]: ...

    def get_task(self, task_id: str) -> Optional[PlannerTaskDetailResponse]: ...

    def cancel_task(self, task_id: str) -> Optional[PlannerTaskDetailResponse]: ...

    def record_permission_decision(self, task_id: str, request: PlannerTaskPermissionDecisionRequest) -> Optional[PlannerTaskDetailResponse]: ...

    async def resume_task(self, task_id: str, request: PlannerTaskResumeRequest) -> Optional[ChatMessageResponse]: ...

    async def retry_task(self, task_id: str) -> Optional[ChatMessageResponse]: ...


def _create_planner_agent_service() -> PlannerApplicationService:
    if CADCOPILOT_PLANNER_STORE_PATH:
        return PlannerAgentService(store=JsonPlannerStore(CADCOPILOT_PLANNER_STORE_PATH))
    return PlannerAgentService()


planner_agent_service: PlannerApplicationService = _create_planner_agent_service()
