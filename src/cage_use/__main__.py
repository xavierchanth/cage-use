"""Run the cage-use MCP v0 stdio server."""

from .mcp import create_server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
