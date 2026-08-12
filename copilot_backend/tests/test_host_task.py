import json
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.gateway_provider import GatewayAgentProvider  # noqa: E402
from agent.host_task import AgentTaskRequest, run_host_task  # noqa: E402
from cadmcp.tool_registry import ToolDefinition  # noqa: E402
from delivery.service import DeliveryService  # noqa: E402
from delivery.store import DeliveryStore  # noqa: E402
from gateway.provider_client import ModelProviderSettings  # noqa: E402
from mcp import types as mcp_types  # noqa: E402


class FakeProvider:
    protocol = "openai_chat"

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    async def complete(self, messages, tools):
        step = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return step


class FakeHostExecutor:
    def __init__(self) -> None:
        self.calls: list = []

    def list_tools(self):
        read = mcp_types.Tool(
            name="blender_scene_summary",
            title="场景摘要",
            description="summary",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            annotations=mcp_types.ToolAnnotations(
                title="s", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
            ),
            _meta={"hostmcp/riskLevel": "read_only", "hostmcp/dryRunSupported": False},
        )
        write = mcp_types.Tool(
            name="blender_create_cube",
            title="创建立方体",
            description="cube",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
            annotations=mcp_types.ToolAnnotations(
                title="c", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
            ),
            _meta={"hostmcp/riskLevel": "high", "hostmcp/dryRunSupported": True},
        )
        return [read, write]

    def execute_tool_sync(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "blender_scene_summary":
            return {"ok": True, "tool_name": name, "data": {"object_count": 3}, "dry_run": False}
        if arguments.get("dry_run", False) is False and arguments.get("permission_token"):
            return {
                "ok": True,
                "tool_name": name,
                "data": {"object_name": "T1"},
                "dry_run": False,
                "rollback_token": "blender-cube-T1",
            }
        return {
            "ok": True,
            "tool_name": name,
            "data": {"preview": {"object_name": "T1"}},
            "dry_run": True,
            "requires_permission": True,
            "permission_token": "ticket-1",
            "preview_hash": "hash-1",
        }


class FakeCadExecutor:
    def __init__(self) -> None:
        self.calls: list = []

    async def execute_tool(self, tool_name, arguments=None, *, caller="", timeout_ms=30000, dry_run=False):
        self.calls.append((tool_name, dict(arguments or {}), dry_run))
        if tool_name == "cad_health_check":
            return {"ok": True, "result": {"status": "ok"}, "dry_run": False}
        if not dry_run and arguments.get("permission_token"):
            return {"ok": True, "result": {"applied": True}, "dry_run": False}
        return {
            "ok": True,
            "result": {"preview": {}},
            "dry_run": True,
            "requires_permission": True,
            "permission_token": "cad-ticket",
            "preview_hash": "cad-hash",
        }


class HostTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_loop_executes_host_tools_and_records_delivery(self) -> None:
        executor = FakeHostExecutor()
        root = Path(tempfile.mkdtemp(prefix="ab-task-"))
        delivery = DeliveryService(store=DeliveryStore(path=root / "deliveries.json"))
        provider = FakeProvider(
            [
                {
                    "content": "检查场景",
                    "tool_calls": [{"id": "c1", "name": "blender_scene_summary", "arguments": {}}],
                },
                {
                    "content": "创建立方体",
                    "tool_calls": [{"id": "c2", "name": "blender_create_cube", "arguments": {"name": "T1"}}],
                },
                {"content": "完成", "tool_calls": []},
            ]
        )
        request = AgentTaskRequest(message="查看场景并创建一个立方体 T1", approval="full")
        result = await run_host_task(
            request,
            executor=executor,  # type: ignore[arg-type]
            delivery=delivery,
            provider=provider,  # type: ignore[arg-type]
        )

        names = [item["name"] for item in result["executed_tools"]]
        self.assertEqual(names, ["blender_scene_summary", "blender_create_cube"])
        self.assertTrue(all(item["ok"] for item in result["executed_tools"]))
        self.assertEqual(result["final_text"], "完成")
        self.assertEqual(result["stopped_reason"], "completed")

        applied = [args for name, args in executor.calls if name == "blender_create_cube"]
        self.assertTrue(any(args.get("dry_run") is False and args.get("permission_token") == "ticket-1" for args in applied))

        view = delivery.get(result["task_id"])
        self.assertIsNotNone(view)
        self.assertTrue(view.handoff.summary.startswith("Agent 任务完成"))
        self.assertEqual(len(view.handoff.verification_steps), 2)

    async def test_no_tools_short_circuits(self) -> None:
        class EmptyExecutor:
            def list_tools(self):
                return []

        result = await run_host_task(
            AgentTaskRequest(message="x"),
            executor=EmptyExecutor(),  # type: ignore[arg-type]
        )
        self.assertEqual(result["stopped_reason"], "no_tools")
        self.assertEqual(result["executed_tools"], [])

    async def test_tool_scope_all_routes_host_and_cad(self) -> None:
        host_executor = FakeHostExecutor()
        cad_executor = FakeCadExecutor()
        cad_tools = [
            ToolDefinition(
                tool_name="cad_health_check",
                display_name="health",
                category="cad",
                description="check",
                input_schema={},
                dry_run_supported=False,
                side_effect_level="none",
                result_schema={},
                risk_level="read_only",
            )
        ]
        root = Path(tempfile.mkdtemp(prefix="ab-task-"))
        delivery = DeliveryService(store=DeliveryStore(path=root / "deliveries.json"))
        provider = FakeProvider(
            [
                {"content": "check cad", "tool_calls": [{"id": "c1", "name": "cad_health_check", "arguments": {}}]},
                {
                    "content": "check scene",
                    "tool_calls": [{"id": "c2", "name": "blender_scene_summary", "arguments": {}}],
                },
                {"content": "完成", "tool_calls": []},
            ]
        )
        request = AgentTaskRequest(message="检查 CAD 和场景", approval="full", tool_scope="all")
        result = await run_host_task(
            request,
            executor=host_executor,  # type: ignore[arg-type]
            cad_executor=cad_executor,  # type: ignore[arg-type]
            cad_tools=cad_tools,
            delivery=delivery,
            provider=provider,  # type: ignore[arg-type]
        )
        names = [item["name"] for item in result["executed_tools"]]
        self.assertEqual(names, ["cad_health_check", "blender_scene_summary"])
        self.assertTrue(all(item["ok"] for item in result["executed_tools"]))
        self.assertEqual([call[0] for call in cad_executor.calls], ["cad_health_check"])
        self.assertIn("blender_scene_summary", [call[0] for call in host_executor.calls])


class GatewayAgentProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_chat_tool_calls_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertIn("tools", payload)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "检查场景",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "blender_scene_summary", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        settings = ModelProviderSettings(
            provider="openai",
            display_name="OpenAI",
            api_key="test-key",
            api_base_url="https://example.test/v1",
            model="gpt-x",
            protocol="openai_chat",
            capabilities=("tool_calling",),
        )
        provider = GatewayAgentProvider(settings, transport=httpx.MockTransport(handler))
        native_tools = [
            {
                "type": "function",
                "function": {
                    "name": "blender_scene_summary",
                    "description": "summary",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = await provider.complete([{"role": "user", "content": "hi"}], native_tools)
        self.assertEqual(result["content"], "检查场景")
        self.assertEqual(result["tool_calls"][0]["name"], "blender_scene_summary")
        self.assertEqual(result["tool_calls"][0]["arguments"], {})


class ResponsesRoundTripTests(unittest.TestCase):
    def test_function_call_output_passthrough(self) -> None:
        from agent.tools import to_responses_input, tool_result_message

        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok", "tool_calls": [{"id": "call_1", "name": "x", "arguments": {}}]},
            tool_result_message("openai_responses", "call_1", "{}"),
        ]
        items = to_responses_input(history)
        types = [item.get("type") for item in items]
        self.assertIn("function_call_output", types)
        output = next(item for item in items if item.get("type") == "function_call_output")
        self.assertEqual(output["call_id"], "call_1")

    def test_parse_prefers_call_id(self) -> None:
        from agent.tools import parse_tool_calls

        calls = parse_tool_calls(
            "openai_responses",
            {
                "output": [
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "x",
                        "arguments": "{}",
                    }
                ]
            },
        )
        self.assertEqual(calls[0]["id"], "call_1")


if __name__ == "__main__":
    unittest.main()
