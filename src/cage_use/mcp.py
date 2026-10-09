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
from .service import ServiceDesktop


Coordinate = Annotated[int, Field(strict=True, ge=0, le=16383)]


def create_server(desktop: CageDesktop | ServiceDesktop | None = None,
                  *, close_on_disconnect: bool = True) -> FastMCP:
    desktop = desktop or CageDesktop()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            if close_on_disconnect:
                desktop.close_all()

    server = FastMCP("cage-use", lifespan=lifespan, instructions=(
        "Computer Use for task-specific Cage apps. launch_app creates an owned app ID. "
        "Use get_app_state to inspect its screenshot, then coordinate or keyboard tools. "
        "Actions return a fresh screenshot. Pixels use the screenshot's original dimensions. "
        "No accessibility tree, element_index actions, rich clipboard, or macOS global app access. "
        "close_app ends a session. " + (
            "Sessions close when this MCP connection exits." if close_on_disconnect else
            "Sessions belong to the connected service and survive MCP disconnects. "
            "Use list_apps to recover existing app IDs after reconnecting.")))

    def state(snapshot: tuple[dict, bytes]) -> CallToolResult:
        metadata, png = snapshot
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
        """List owned Cage app IDs and running state, including reconnectable service apps."""
        return desktop.list_apps()

    @server.tool(annotations=read_only)
    def get_app_state(app: str, disableDiff: bool = False) -> CallToolResult:
        """Return a native MCP PNG image and state metadata. Always a full snapshot.

        disableDiff is accepted for Sky-style callers; no accessibility diffs exist.
        This never launches an app implicitly: use launch_app first.
        """
        return state(desktop.capture(app))

    @server.tool(annotations=action)
    def click(app: str, x: Coordinate | None = None, y: Coordinate | None = None,
              mouse_button: Button = "left", click_count: Annotated[int, Field(strict=True, ge=1, le=3)] = 1,
              element_index: int | None = None) -> CallToolResult:
        """Click screenshot coordinates in the app; element_index is unsupported."""
        return state(desktop.interact("click", app, x, y, mouse_button, click_count, element_index))

    @server.tool(annotations=action)
    def drag(app: str, from_x: Coordinate, from_y: Coordinate,
             to_x: Coordinate, to_y: Coordinate) -> CallToolResult:
        """Drag the left mouse button between screenshot coordinates."""
        return state(desktop.interact("drag", app, from_x, from_y, to_x, to_y))

    @server.tool(annotations=action)
    def scroll(app: str, direction: Direction, x: Coordinate, y: Coordinate,
               pages: Annotated[int, Field(strict=True, ge=1, le=10)] = 1,
               element_index: int | None = None) -> CallToolResult:
        """Scroll at screenshot coordinates. Each page is eight wheel steps."""
        return state(desktop.interact("scroll", app, direction, pages, x, y, element_index))

    @server.tool(annotations=action)
    def press_key(app: str, key: Annotated[str, Field(min_length=1, max_length=128)]) -> CallToolResult:
        """Press an XKB/xdotool-style key or chord, such as Return or ctrl+a."""
        return state(desktop.interact("press_key", app, key))

    @server.tool(annotations=action)
    def type_text(app: str, text: Annotated[str, Field(max_length=10000)]) -> CallToolResult:
        """Type UTF-8 text. Newlines can submit forms; this is not clipboard paste."""
        return state(desktop.interact("type_text", app, text))

    @server.tool(annotations=action)
    def close_app(app: str) -> dict:
        """Stop this owned Cage app and clean up its display and VNC processes."""
        return desktop.close(app)

    @server.tool(annotations=action)
    def start_recording(app: str) -> dict:
        """Start a silent 30 fps MP4 recording of this app's Cage display.

        Returns a file path on the host running Cage. Recordings survive app
        cleanup. Service-owned recordings continue through MCP reconnects.
        """
        return desktop.start_recording(app)

    @server.tool(annotations=action)
    def stop_recording(app: str) -> dict:
        """Finalize the app's recording and return its host-local MP4 path and size.

        Stopping again returns the same completed recording. For a remote host,
        copy the returned path over SSH to view the video on the client.
        """
        return desktop.stop_recording(app)

    return server
