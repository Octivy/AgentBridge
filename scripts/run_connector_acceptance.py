from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copilot_backend"))
sys.path.insert(0, str(ROOT))

from acceptance.runner import ConnectorAcceptanceRunner, write_report  # noqa: E402


async def run(args: argparse.Namespace) -> int:
    runner = ConnectorAcceptanceRunner(
        ROOT,
        mcp_repeat=args.mcp_repeat,
        provider_repeat=args.provider_repeat,
        bridge_repeat=args.bridge_repeat,
        provider=args.provider,
    )
    report = await runner.run()
    json_path, markdown_path = write_report(report, (ROOT / args.report_dir).resolve())
    print(f"status={report.status}")
    print(f"json={json_path}")
    print(f"markdown={markdown_path}")
    for check in report.checks:
        print(f"{check.check_id}={check.status} {check.summary}")
    return 0 if report.status == "passed" else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AgentBridge connector V1/V2 acceptance gates.")
    parser.add_argument("--mcp-repeat", type=int, default=20)
    parser.add_argument("--provider-repeat", type=int, default=10)
    parser.add_argument("--bridge-repeat", type=int, default=20)
    parser.add_argument("--provider", default="auto", choices=["auto", "openai", "anthropic", "deepseek", "minimax", "ollama"])
    parser.add_argument("--report-dir", default="docs/validation")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
