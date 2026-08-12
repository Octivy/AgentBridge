"""Backward-compatible launcher for the standalone cadmcp package."""

from cadmcp.server import main, mcp

__all__ = ["main", "mcp"]


if __name__ == "__main__":
    main()
