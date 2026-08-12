import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapter_install.rhino import (  # noqa: E402
    STARTUP_NAME,
    detect_rhino_versions,
    install_rhino_adapter,
    rhino_adapter_status,
)


class RhinoInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ab-rh-"))
        (self.root / "8.0").mkdir(parents=True)
        (self.root / "7.0").mkdir(parents=True)

    def test_detect_versions_newest_first(self) -> None:
        self.assertEqual(detect_rhino_versions(self.root), ["8.0", "7.0"])

    def test_install_and_status(self) -> None:
        result = install_rhino_adapter(root=self.root, repo_root=Path(__file__).resolve().parents[2])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["installed"]), 2)
        package = self.root / "8.0" / "scripts" / "agentbridge_rhino"
        self.assertTrue((package / "backend.py").exists())
        self.assertTrue((self.root / "8.0" / "scripts" / STARTUP_NAME).exists())
        status = rhino_adapter_status(self.root)
        self.assertTrue(status["adapters"][0]["installed"])
        self.assertTrue(status["adapters"][0]["autostart"])

    def test_install_no_rhino(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="ab-rh-empty-"))
        result = install_rhino_adapter(root=empty, repo_root=Path(__file__).resolve().parents[2])
        self.assertFalse(result["ok"])
        self.assertEqual(result["rhino_versions"], [])


if __name__ == "__main__":
    unittest.main()
