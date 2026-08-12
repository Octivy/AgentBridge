import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapter_install.sketchup import (  # noqa: E402
    EXTENSION_NAME,
    detect_sketchup_versions,
    install_sketchup_extension,
    sketchup_extension_status,
)


class SketchupInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ab-skp-"))
        (self.root / "SketchUp 2025").mkdir(parents=True)
        (self.root / "SketchUp 2021").mkdir(parents=True)

    def test_detect_versions_newest_first(self) -> None:
        self.assertEqual(detect_sketchup_versions(self.root), ["2025", "2021"])

    def test_install_and_status(self) -> None:
        result = install_sketchup_extension(root=self.root, repo_root=Path(__file__).resolve().parents[2])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["installed"]), 2)
        target = self.root / "SketchUp 2025" / "SketchUp" / "Extensions" / EXTENSION_NAME
        self.assertTrue(target.exists())
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"cadcopilot_extension.rb", "cadcopilot_host.rb"},
            )
        status = sketchup_extension_status(self.root)
        self.assertTrue(status["extensions"][0]["installed"])

    def test_install_no_sketchup(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="ab-skp-empty-"))
        result = install_sketchup_extension(root=empty, repo_root=Path(__file__).resolve().parents[2])
        self.assertFalse(result["ok"])
        self.assertEqual(result["sketchup_versions"], [])


if __name__ == "__main__":
    unittest.main()
