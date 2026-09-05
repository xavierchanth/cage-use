"""MCP v0 delivery for cage-use."""
from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import Field

from .session import Button, CageDesktop, Direction


Coordinate = Annotated[int, Field(strict=True, ge=0, le=16383)]


def create_server(desktop: CageDesktop | None = None) -> FastMCP:
    desktop = desktop or CageDesktop()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            desktop.close_all()

    server = FastMCP("cage-use", lifespan=lifespan, instructions=(
        "Computer Use for task-specific Cage apps. launch_app creates an owned app ID. "
        "Use get_app_state to inspect its screenshot, then coordinate or keyboard tools. "
        "Actions return a fresh screenshot. Pixels use the screenshot's original dimensions. "
        "No accessibility tree, element_index actions, rich clipboard, or macOS global app access. "
        "close_app ends a session. Sessions close when this MCP connection exits."))

    def state(app: str) -> CallToolResult:
        metadata, png = desktop.capture(app)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(metadata)),
                                     ImageContent(type="image", mimeType="image/png",
                                                  data=base64.b64encode(png).decode())],
                              structuredContent=metadata)

    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    action = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)

    @server.tool(annotations=action)
    def launch_app(executable: str, args: list[str] | None = None) -> dict:
        """Launch a chosen executable in a new Cage session; returns its app ID.

        Arguments are literal argv entries, not a shell command. Browser sessions
        may need separate profiles. Use get_app_state next to inspect the app.
        """
        return desktop.launch(executable, args or [])

    @server.tool(annotations=read_only)
    def list_apps() -> list[dict]:
        """List this MCP connection's Cage app IDs and running state."""
        return desktop.list_apps()

    @server.tool(annotations=read_only)
    def get_app_state(app: str, disableDiff: bool = False) -> CallToolResult:
        """Return a native MCP PNG image and state metadata. Always a full snapshot.

        disableDiff is accepted for Sky-style callers; no accessibility diffs exist.
        This never launches an app implicitly: use launch_app first.
        """
        return state(app)

    @server.tool(annotations=action)
    def click(app: str, x: Coordinate | None = None, y: Coordinate | None = None,
              mouse_button: Button = "left", click_count: Annotated[int, Field(strict=True, ge=1, le=3)] = 1,
              element_index: int | None = None) -> CallToolResult:
        """Click screenshot coordinates in the app; element_index is unsupported."""
        with desktop.lock:
            desktop.click(app, x, y, mouse_button, click_count, element_index)
            return state(app)

    @server.tool(annotations=action)
    def drag(app: str, from_x: Coordinate, from_y: Coordinate,
             to_x: Coordinate, to_y: Coordinate) -> CallToolResult:
        """Drag the left mouse button between screenshot coordinates."""
        with desktop.lock:
            desktop.drag(app, from_x, from_y, to_x, to_y)
            return state(app)

    @server.tool(annotations=action)
    def scroll(app: str, direction: Direction, x: Coordinate, y: Coordinate,
               pages: Annotated[int, Field(strict=True, ge=1, le=10)] = 1,
               element_index: int | None = None) -> CallToolResult:
        """Scroll at screenshot coordinates. Each page is eight wheel steps."""
        with desktop.lock:
            desktop.scroll(app, direction, pages, x, y, element_index)
            return state(app)

    @server.tool(annotations=action)
    def press_key(app: str, key: Annotated[str, Field(min_length=1, max_length=128)]) -> CallToolResult:
        """Press an XKB/xdotool-style key or chord, such as Return or ctrl+a."""
        with desktop.lock:
            desktop.press_key(app, key)
            return state(app)

    @server.tool(annotations=action)
    def type_text(app: str, text: Annotated[str, Field(max_length=10000)]) -> CallToolResult:
        """Type UTF-8 text. Newlines can submit forms; this is not clipboard paste."""
        with desktop.lock:
            desktop.type_text(app, text)
            return state(app)

    @server.tool(annotations=action)
    def close_app(app: str) -> dict:
        """Stop this owned Cage app and clean up its display and VNC processes."""
        return desktop.close(app)

    return server
