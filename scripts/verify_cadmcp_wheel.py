from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel")
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if not any(name.endswith("cadmcp/server.py") for name in names):
            raise RuntimeError("cadmcp server is missing from wheel")
        required_modules = {
            "cadmcp/domain/architecture/functional_objects.py",
            "cadmcp/domain/architecture/layer_mapping.py",
            "cadmcp/domain/architecture/outer_outline.py",
            "cadmcp/tools/architecture.py",
        }
        missing_modules = sorted(required_modules.difference(names))
        if missing_modules:
            raise RuntimeError(
                f"architecture modules are missing from wheel: {missing_modules}"
            )
        forbidden = [name for name in names if name.startswith("copilot_backend/")]
        if forbidden:
            raise RuntimeError(f"wheel unexpectedly contains backend modules: {forbidden[:5]}")
    print(f"verified {wheel.name}: {len(names)} entries")


if __name__ == "__main__":
    main()
