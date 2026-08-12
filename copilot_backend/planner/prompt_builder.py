from typing import Any, Dict, List

from cadmcp.tool_registry import list_product_tools
from planner.session import PlannerObservation, PlannerSessionState
from skills.registry import list_skills


class PlannerPromptBuilder:
    """Build structured model input for a Planner session.

    This builder intentionally returns a plain dictionary so the future model
    gateway can decide whether to convert it to messages, JSON schema requests,
    or other provider-specific payloads.
    """

    def build(self, state: PlannerSessionState) -> Dict[str, Any]:
        return {
            "session_id": state.session_id,
            "mode": state.mode,
            "user_goal": state.user_goal,
            "last_user_message": state.last_user_message,
            "current_iteration": state.current_iteration,
            "max_iterations": state.max_iterations,
            "task_status": state.task_status.value,
            "context_snapshot": state.context_snapshot,
            "agent_approval": state.agent_approval,
            "pending_steps": list(state.pending_steps),
            "completed_steps": list(state.completed_steps),
            "current_selected_skills": list(state.selected_skills),
            "recent_observations": self._serialize_observations(state.memory[-8:]),
            "last_model_decision": self._serialize_last_decision(state),
            "available_tools": self._serialize_tools(),
            "available_skills": self._serialize_skills(),
            "response_contract": {
                "required_fields": [
                    "intent",
                    "reasoning_summary",
                    "next_action",
                    "tool_calls",
                    "selected_skills",
                    "completion_check",
                    "user_message",
                    "ask_user_type",
                    "ask_user_hint",
                    "suggested_steps",
                ],
                "allowed_next_actions": ["respond", "ask_user", "call_tool", "finish"],
                "tool_selection_guidance": "优先参考 available_skills 中的技能定义和 mcp_tools，再选择需要的 tool_calls。",
            },
        }

    @staticmethod
    def _serialize_skills() -> List[Dict[str, Any]]:
        return [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "category": skill.category,
                "mcp_tools": list(skill.mcp_tools),
                "auto_tool_calls": [
                    {
                        "tool_name": tool_call.tool_name,
                        "arguments": dict(tool_call.arguments),
                    }
                    for tool_call in skill.auto_tool_calls
                ],
                "parameters": [
                    {
                        "name": parameter.name,
                        "label": parameter.label,
                        "value_type": parameter.value_type,
                        "required": parameter.required,
                        "default_value": parameter.default_value,
                        "options": list(parameter.options),
                        "description": parameter.description,
                    }
                    for parameter in skill.parameters
                ],
                "planner_hints": list(skill.planner_hints),
                "examples": list(skill.examples),
                "acceptance_examples": [
                    {
                        "title": example.title,
                        "user_message": example.user_message,
                        "expected_behavior": example.expected_behavior,
                        "manual_test": example.manual_test,
                    }
                    for example in skill.acceptance_examples
                ],
            }
            for skill in list_skills(enabled_only=True)
        ]

    @staticmethod
    def _serialize_tools() -> List[Dict[str, Any]]:
        return [
            {
                "tool_name": tool.tool_name,
                "display_name": tool.display_name,
                "category": tool.category,
                "description": tool.description,
                "dry_run_supported": tool.dry_run_supported,
                "side_effect_level": tool.side_effect_level,
                "input_schema": tool.input_schema,
                "result_schema": tool.result_schema,
            }
            for tool in list_product_tools()
        ]

    @staticmethod
    def _serialize_observations(observations: List[PlannerObservation]) -> List[Dict[str, Any]]:
        return [
            {
                "source": observation.source,
                "payload": observation.payload,
                "is_error": observation.is_error,
            }
            for observation in observations
        ]

    @staticmethod
    def _serialize_last_decision(state: PlannerSessionState) -> Dict[str, Any]:
        decision = state.last_model_decision
        if decision is None:
            return {}

        return {
            "intent": decision.intent,
            "reasoning_summary": decision.reasoning_summary,
            "next_action": decision.next_action.value,
            "tool_calls": [
                {
                    "tool_name": tool_call.tool_name,
                    "arguments": tool_call.arguments,
                }
                for tool_call in decision.tool_calls
            ],
            "selected_skills": list(decision.selected_skills),
            "completion_check": decision.completion_check,
            "user_message": decision.user_message,
            "ask_user_type": decision.ask_user_type,
            "ask_user_hint": decision.ask_user_hint,
            "suggested_steps": list(decision.suggested_steps),
        }
