"""Run the cage-use MCP v0 stdio server."""

import argparse
from collections.abc import Sequence

from .mcp import create_server
from .service import ServiceDesktop, serve


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="cage-mcp",
        description="Run the cage-use MCP server over stdio.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", metavar="SOCKET", help="Own persistent apps through a private Unix socket.")
    mode.add_argument("--connect", metavar="SOCKET", help="Run MCP stdio connected to a persistent session service.")
    options = parser.parse_args(argv)
    if options.serve:
        serve(options.serve)
    elif options.connect:
        create_server(ServiceDesktop(options.connect), close_on_disconnect=False).run(transport="stdio")
    else:
        create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
