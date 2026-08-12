import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shared.settings as settings


class SettingsProviderDefaultsTests(unittest.TestCase):
    def test_official_api_key_does_not_fallback_to_minimax_key(self) -> None:
        original_env = dict(os.environ)
        try:
            with patch.dict(
                os.environ,
                {
                    "PYTHON_DOTENV_DISABLED": "true",
                    "MINIMAX_API_KEY": "minimax-only-key",
                },
                clear=True,
            ):
                reloaded = importlib.reload(settings)

            self.assertEqual(reloaded.CADCOPILOT_OFFICIAL_API_KEY, "")
            self.assertEqual(reloaded.MINIMAX_API_KEY, "minimax-only-key")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings)


if __name__ == "__main__":
    unittest.main()
