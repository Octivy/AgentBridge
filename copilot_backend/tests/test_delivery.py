import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from delivery.models import DeliverableCreate, HandoffUpdate  # noqa: E402
from delivery.service import DeliveryService  # noqa: E402
from delivery.store import DeliveryStore  # noqa: E402


class DeliveryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ab-delivery-"))
        store = DeliveryStore(path=self.root / "deliveries.json")
        self.service = DeliveryService(store=store)

    def test_add_deliverable_and_handoff(self) -> None:
        view = self.service.add_deliverable(
            "task-1",
            DeliverableCreate(
                name="scene.png",
                kind="screenshot",
                path=r"C:\tmp\scene.png",
                description="渲染结果",
            ),
        )
        self.assertEqual(view.task_id, "task-1")
        self.assertEqual(view.deliverable_count, 1)
        self.assertEqual(view.deliverables[0].kind, "screenshot")

        view = self.service.set_handoff(
            "task-1",
            HandoffUpdate(
                summary="已完成场景整理",
                verification_steps=["打开 scene.png 检查"],
                next_steps=["提交给用户确认"],
            ),
        )
        self.assertEqual(view.handoff.summary, "已完成场景整理")
        self.assertEqual(view.handoff.verification_steps, ["打开 scene.png 检查"])

        got = self.service.get("task-1")
        self.assertIsNotNone(got)
        self.assertEqual(got.handoff.next_steps, ["提交给用户确认"])
        self.assertIsNone(self.service.get("missing"))

    def test_deliverable_same_name_replaces(self) -> None:
        self.service.add_deliverable(
            "task-2",
            DeliverableCreate(name="report.md", kind="report", path=r"C:\tmp\v1.md"),
        )
        view = self.service.add_deliverable(
            "task-2",
            DeliverableCreate(name="report.md", kind="report", path=r"C:\tmp\v2.md"),
        )
        self.assertEqual(view.deliverable_count, 1)
        self.assertEqual(view.deliverables[0].path, r"C:\tmp\v2.md")

    def test_list_orders_by_updated(self) -> None:
        self.service.add_deliverable("a", DeliverableCreate(name="f", path="p"))
        self.service.add_deliverable("b", DeliverableCreate(name="f", path="p"))
        views = self.service.list()
        self.assertEqual([v.task_id for v in views][:2], ["b", "a"])

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.service.add_deliverable("", DeliverableCreate(name="x", path="p"))
        with self.assertRaises(ValueError):
            self.service.add_deliverable("t", DeliverableCreate(name="", path="p"))
        with self.assertRaises(ValueError):
            self.service.add_deliverable("t", DeliverableCreate(name="x", path=""))


if __name__ == "__main__":
    unittest.main()
