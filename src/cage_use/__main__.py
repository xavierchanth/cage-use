"""Run the cage-use MCP v0 stdio server."""

import argparse
from collections.abc import Sequence

from .mcp import create_server


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="cage-mcp",
        description="Run the cage-use MCP server over stdio.",
    )
    parser.parse_args(argv)
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
