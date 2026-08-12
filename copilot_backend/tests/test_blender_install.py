import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapter_install.blender import (  # noqa: E402
    STARTUP_NAME,
    blender_addon_status,
    detect_blender_versions,
    install_blender_addon,
)


class BlenderInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ab-bl-"))
        (self.root / "5.1").mkdir(parents=True)
        (self.root / "4.2").mkdir(parents=True)

    def test_detect_versions_newest_first(self) -> None:
        self.assertEqual(detect_blender_versions(self.root), ["5.1", "4.2"])

    def test_install_and_status(self) -> None:
        result = install_blender_addon(root=self.root, repo_root=Path(__file__).resolve().parents[2])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["installed"]), 2)
        addon = self.root / "5.1" / "scripts" / "addons" / "agentbridge_host"
        self.assertTrue((addon / "__init__.py").exists())
        self.assertTrue((self.root / "5.1" / "scripts" / "startup" / STARTUP_NAME).exists())
        status = blender_addon_status(self.root)
        self.assertTrue(status["addons"][0]["installed"])
        self.assertTrue(status["addons"][0]["autostart"])

    def test_install_no_blender(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="ab-bl-empty-"))
        result = install_blender_addon(root=empty, repo_root=Path(__file__).resolve().parents[2])
        self.assertFalse(result["ok"])
        self.assertEqual(result["blender_versions"], [])


if __name__ == "__main__":
    unittest.main()
