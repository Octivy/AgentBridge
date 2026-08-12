from typing import Dict, List, Optional

from planner.session import PlannerSession, PlannerSessionState


class InMemoryPlannerStore:
    """Minimal in-memory session store for early Planner integration."""

    def __init__(self) -> None:
        self._sessions: Dict[str, PlannerSession] = {}

    def create(self, state: PlannerSessionState) -> PlannerSession:
        session = PlannerSession(state)
        self._sessions[state.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[PlannerSession]:
        return self._sessions.get(session_id)

    def save(self, session: PlannerSession) -> PlannerSession:
        self._sessions[session.state.session_id] = session
        return session

    def list_sessions(self) -> List[PlannerSession]:
        return list(self._sessions.values())

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
