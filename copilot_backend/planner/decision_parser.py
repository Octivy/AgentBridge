import json
import re
from typing import Any, Dict, List

from cadmcp.tool_registry import get_product_tool
from planner.session import PlannerActionType, PlannerDecision, ToolCallSpec
from skills.registry import get_enabled_skill


class PlannerDecisionParserError(ValueError):
    pass


class PlannerDecisionParser:
    """Parse structured model decisions into PlannerDecision objects."""

    def parse(self, payload: Any) -> PlannerDecision:
        data = self._normalize_payload(payload)

        next_action_raw = str(data.get("next_action", "")).strip().lower()
        if not next_action_raw:
            raise PlannerDecisionParserError("Planner decision is missing next_action.")

        try:
            next_action = PlannerActionType(next_action_raw)
        except ValueError as exc:
            raise PlannerDecisionParserError(f"Unsupported next_action: {next_action_raw}") from exc

        tool_calls = self._parse_tool_calls(data.get("tool_calls", []))
        selected_skills = self._parse_selected_skills(data.get("selected_skills", []))
        if next_action == PlannerActionType.CALL_TOOL and not tool_calls and not selected_skills:
            raise PlannerDecisionParserError("call_tool decision requires tool_calls or selected_skills.")

        return PlannerDecision(
            intent=str(data.get("intent", "")).strip(),
            reasoning_summary=str(data.get("reasoning_summary", "")).strip(),
            next_action=next_action,
            tool_calls=tool_calls,
            selected_skills=selected_skills,
            completion_check=bool(data.get("completion_check", False)),
            user_message=str(data.get("user_message", "")).strip(),
            ask_user_type=str(data.get("ask_user_type", "")).strip(),
            ask_user_hint=str(data.get("ask_user_hint", "")).strip(),
            suggested_steps=self._parse_string_list(data.get("suggested_steps", []), "suggested_steps"),
        )

    @staticmethod
    def _normalize_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload

        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                raise PlannerDecisionParserError("Planner decision payload is empty.")

            try:
                parsed = PlannerDecisionParser._parse_json_object(text)
            except json.JSONDecodeError as exc:
                extracted = PlannerDecisionParser._extract_json_object_text(text)
                if not extracted:
                    raise PlannerDecisionParserError(f"Planner decision is not valid JSON: {exc}") from exc

                try:
                    parsed = PlannerDecisionParser._parse_json_object(extracted)
                except json.JSONDecodeError as nested_exc:
                    raise PlannerDecisionParserError(f"Planner decision is not valid JSON: {nested_exc}") from nested_exc

            return parsed

        raise PlannerDecisionParserError(f"Unsupported planner decision payload type: {type(payload).__name__}")

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise PlannerDecisionParserError("Planner decision JSON must be an object.")

        return parsed

    @staticmethod
    def _extract_json_object_text(text: str) -> str:
        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced_match:
            return fenced_match.group(1).strip()

        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue

            try:
                parsed, end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                return text[index:index + end].strip()

        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            return text[first:last + 1].strip()

        return ""

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: Any) -> List[ToolCallSpec]:
        if raw_tool_calls is None:
            return []
        if not isinstance(raw_tool_calls, list):
            raise PlannerDecisionParserError("tool_calls must be a list.")

        parsed: List[ToolCallSpec] = []
        for item in raw_tool_calls:
            if not isinstance(item, dict):
                raise PlannerDecisionParserError("Each tool call must be an object.")

            tool_name = str(item.get("tool_name", "")).strip()
            if not tool_name:
                raise PlannerDecisionParserError("tool_name is required for each tool call.")
            if get_product_tool(tool_name) is None:
                raise PlannerDecisionParserError(f"Unsupported tool_name: {tool_name}")

            arguments = item.get("arguments", {})
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                raise PlannerDecisionParserError("tool call arguments must be an object.")

            parsed.append(ToolCallSpec(tool_name=tool_name, arguments=arguments))

        return parsed

    @staticmethod
    def _parse_string_list(value: Any, field_name: str) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise PlannerDecisionParserError(f"{field_name} must be a list.")

        parsed: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                parsed.append(text)
        return parsed

    @staticmethod
    def _parse_selected_skills(value: Any) -> List[str]:
        parsed = PlannerDecisionParser._parse_string_list(value, "selected_skills")
        for skill_id in parsed:
            if get_enabled_skill(skill_id) is None:
                raise PlannerDecisionParserError(f"Unsupported skill_id: {skill_id}")
        return parsed
