from __future__ import annotations

import argparse
import asyncio
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copilot_backend"))

from gateway.provider_client import call_provider  # noqa: E402
from shared.schemas import ChatMessageRequest  # noqa: E402


async def run(args: argparse.Namespace) -> None:
    image = ""
    if args.image:
        image = base64.b64encode(Path(args.image).read_bytes()).decode("ascii")
    request = ChatMessageRequest(
        message=args.message,
        provider=args.provider,
        model=args.model or None,
        api_key=args.api_key or None,
        api_base_url=args.base_url or None,
        protocol=args.protocol or None,
        capabilities=args.capability,
        image_base64=image or None,
        stream=args.stream,
    )
    result = await call_provider(request)
    if not result.strip():
        raise RuntimeError("Provider returned an empty response")
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Optional online model-provider smoke test")
    parser.add_argument("--provider", required=True, choices=["openai", "anthropic", "deepseek", "minimax", "ollama", "openai_compatible", "enterprise_private"])
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default=os.getenv("MODEL_API_KEY", ""))
    parser.add_argument("--protocol", default="")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--image", default="")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--message", default="Reply with the single word OK.")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
