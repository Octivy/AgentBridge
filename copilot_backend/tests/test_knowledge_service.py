import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.service import ModelGatewayResult
from knowledge.service import KnowledgeIndex, KnowledgeQueryService
from shared.schemas import KnowledgeQueryRequest


class _FakeGateway:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    async def request_text_result(self, request, system_prompt, user_prompt):
        self.calls.append((request, system_prompt, user_prompt))
        return ModelGatewayResult(
            text=self.answer,
            provider="enterprise_private",
            provider_display_name="Company",
            model="company-model",
            trace_id=request.trace_id or "",
        )


class KnowledgeServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "approved-standards"
        self.root.mkdir()
        (self.root / "parking.md").write_text(
            "# 企业车库设计规则\n"
            "version: 2026-Q2\n\n"
            "## 车位与车道\n"
            "标准车位宽度不得小于 2.4 米，车道宽度应按内部审查表复核。\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_index_returns_relative_source_and_version(self):
        results = KnowledgeIndex([self.root]).search("标准车位宽度", limit=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].citation_id, "S1")
        self.assertEqual(results[0].source, "approved-standards/parking.md")
        self.assertEqual(results[0].version, "2026-Q2")
        self.assertIn("2.4 米", results[0].excerpt)

    async def test_grounded_answer_requires_valid_source_marker(self):
        gateway = _FakeGateway("标准车位宽度不得小于 2.4 米。[S1]")
        service = KnowledgeQueryService(KnowledgeIndex([self.root]), gateway)
        result = await service.query(
            KnowledgeQueryRequest(
                question="标准车位宽度是多少？",
                provider="enterprise_private",
                api_base_url="http://company-model/v1",
                model="company-model",
            )
        )
        self.assertTrue(result.grounded)
        self.assertEqual(result.warning, "")
        self.assertIn("来源：", result.answer)
        self.assertEqual(len(gateway.calls), 1)

    async def test_missing_source_does_not_call_model(self):
        gateway = _FakeGateway("不应调用")
        service = KnowledgeQueryService(KnowledgeIndex([self.root]), gateway)
        result = await service.query(KnowledgeQueryRequest(question="完全无关的量子问题"))
        self.assertFalse(result.grounded)
        self.assertEqual(result.answer, "")
        self.assertIn("未调用模型", result.warning)
        self.assertEqual(gateway.calls, [])

    async def test_answer_without_citation_is_not_grounded(self):
        gateway = _FakeGateway("标准车位宽度不得小于 2.4 米。")
        service = KnowledgeQueryService(KnowledgeIndex([self.root]), gateway)
        result = await service.query(KnowledgeQueryRequest(question="标准车位宽度是多少？"))
        self.assertFalse(result.grounded)
        self.assertIn("未包含来源编号", result.warning)


if __name__ == "__main__":
    unittest.main()
