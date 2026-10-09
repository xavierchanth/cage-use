#!/usr/bin/env python3
"""Backend contract tests and a real MCP stdio handshake using a fake display."""
from __future__ import annotations

from io import BytesIO, StringIO
from contextlib import contextmanager
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from cage_use.mcp import create_server
from cage_use.__main__ import main
from cage_use.session import CageDesktop, Session
from cage_use.service import ServiceDesktop, SessionService
from PIL import Image


def png_bytes():
    output = BytesIO()
    Image.new("RGB", (800, 600), "white").save(output, "PNG")
    return output.getvalue()


@contextmanager
def fake_recorder():
    """A real child process that flushes its output when interrupted."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        binary = root / "wf-recorder"
        binary.write_text(f"#!{sys.executable}\n" + '''import pathlib, signal, sys, time
path = pathlib.Path(sys.argv[sys.argv.index("--file") + 1])
def stop(*args):
    with path.open("ab") as video:
        video.write(b"finalized")
    sys.exit(0)
signal.signal(signal.SIGINT, stop)
path.write_bytes(b"video-header")
while True:
    time.sleep(.01)
''')
        binary.chmod(0o755)
        with patch.dict(os.environ, {"PATH": f"{root}:{os.environ['PATH']}",
                                    "CAGE_USE_RECORDING_DIR": str(root / "recordings")}):
            yield root


class FakeDesktop(CageDesktop):
    def __init__(self):
        super().__init__()
        self.calls = []

    def launch(self, executable, args):
        session = Session("owned", executable, 5905, "wayland-test",
                          Mock(poll=Mock(return_value=None)), tempfile.TemporaryDirectory())
        self.sessions[session.id] = session
        return session.summary()

    def run(self, argv, *, env=None, data=None):
        self.calls.append((argv, env, data))
        return png_bytes() if argv[0] == "grim" else b""

    def stop_process(self, app, process):
        pass

    def close_all(self):
        super().close_all()
        if marker := os.environ.get("CAGE_TEST_CLOSED"):
            Path(marker).write_text("closed")


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.desktop = FakeDesktop()
        self.desktop.launch("test-app", [])
        self.addCleanup(self.desktop.close_all)

    def test_requires_owned_session_and_observed_coordinates(self):
        with self.assertRaises(ValueError):
            self.desktop.capture("not-owned")
        with self.assertRaises(ValueError):
            self.desktop.click("owned", 1, 1, "left", 1, None)
        self.desktop.capture("owned")
        for x, y in [(800, 0), (-1, 0), (0, 600), (True, 1)]:
            with self.assertRaises(ValueError):
                self.desktop.click("owned", x, y, "left", 1, None)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.desktop.click("owned", 1, 1, "left", 1, 42)
        self.assertFalse(any(call[0][0] == "vncdo" for call in self.desktop.calls))

    def test_capture_reports_original_pixel_dimensions(self):
        metadata, png = self.desktop.capture("owned")
        self.assertEqual(metadata["screenshot"]["width"], 800)
        self.assertEqual(metadata["screenshot"]["height"], 600)
        self.assertEqual(metadata["screenshot"]["scale"], 1)
        self.assertFalse(metadata["capabilities"]["accessibility"])
        self.assertEqual(png, png_bytes())

    def test_move_and_click_share_vnc_connection(self):
        self.desktop.capture("owned")
        self.desktop.click("owned", 10, 20, "right", 2, None)
        self.assertEqual(self.desktop.calls[-1][0], ["vncdo", "-s", "127.0.0.1::5905",
                         "move", "10", "20", "click", "3", "pause", "0.08", "click", "3"])

    def test_drag_path_is_bounded_and_releases_at_exact_destination(self):
        self.desktop.capture("owned")
        for start, end in [((1, 2), (799, 599)), ((799, 599), (1, 2)),
                           ((10, 20), (10, 25)), ((10, 20), (10, 20))]:
            with self.subTest(start=start, end=end):
                before = len(self.desktop.calls)
                self.desktop.drag("owned", *start, *end)
                self.assertEqual(len(self.desktop.calls), before + 1)
                argv = self.desktop.calls[-1][0]
                self.assertEqual(argv[:3], ["vncdo", "-s", "127.0.0.1::5905"])
                self.assertNotIn("drag", argv)
                tokens = iter(argv[3:])
                moves, held, duration = [], False, 0
                for command in tokens:
                    if command == "move":
                        point = (int(next(tokens)), int(next(tokens)))
                        self.assertEqual(held, bool(moves))
                        moves.append(point)
                    elif command == "pause":
                        duration += float(next(tokens))
                    elif command == "mousedown":
                        self.assertEqual(next(tokens), "1")
                        self.assertFalse(held)
                        held = True
                    elif command == "mouseup":
                        self.assertEqual(next(tokens), "1")
                        self.assertTrue(held)
                        self.assertEqual(moves[-1], end)
                        held = False
                    else:
                        self.fail(f"Unexpected drag command: {command}")
                self.assertFalse(held)
                self.assertEqual(moves[0], start)
                self.assertLessEqual(len(moves), 21)
                self.assertLess(duration, 0.5)
                for point in moves:
                    for axis in range(2):
                        self.assertLessEqual(min(start[axis], end[axis]), point[axis])
                        self.assertLessEqual(point[axis], max(start[axis], end[axis]))

    def test_drag_validates_both_endpoints_before_sending_input(self):
        with self.assertRaises(ValueError):
            self.desktop.drag("owned", 1, 2, 30, 40)
        self.desktop.capture("owned")
        for coordinates in [(800, 0, 1, 2), (1, 2, 0, 600), (1, 2, True, 3)]:
            with self.assertRaises(ValueError):
                self.desktop.drag("owned", *coordinates)
        self.assertFalse(any(call[0][0] == "vncdo" for call in self.desktop.calls))

    def test_scroll_is_bounded(self):
        self.desktop.capture("owned")
        self.desktop.scroll("owned", "down", 1, 10, 20, None)
        self.assertEqual(self.desktop.calls[-1][0].count("click"), 8)

    def test_text_is_stdin_not_shell_or_cli_options(self):
        text = '--help $(touch /tmp/never)\nλ'
        self.desktop.type_text("owned", text)
        argv, env, data = self.desktop.calls[-1]
        self.assertEqual(argv, ["wtype", "-"])
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-test")
        self.assertEqual(data, text.encode())

    def test_key_chords_release_modifiers(self):
        self.desktop.press_key("owned", "ctrl+shift+a")
        self.assertEqual(self.desktop.calls[-1][0],
                         ["wtype", "-M", "ctrl", "-M", "shift", "-k", "a", "-m", "shift", "-m", "ctrl"])
        with self.assertRaises(ValueError):
            self.desktop.press_key("owned", "bad+a")

    def test_close_drops_ownership_and_preserves_other_apps(self):
        self.desktop.close("owned")
        self.assertEqual(self.desktop.list_apps(), [])
        with self.assertRaises(ValueError):
            self.desktop.close("unrelated")

    def test_cleanup_uses_owned_unit_not_port(self):
        process = Mock(pid=1234, poll=Mock(return_value=0))
        with patch("subprocess.run") as run:
            CageDesktop.stop_process("unique-id", process)
        self.assertEqual(run.call_args.args[0],
                         ["systemctl", "--user", "stop", "cage-session-unique-id.scope"])

    def test_tool_failure_is_not_retried(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("wtype", 15)) as run:
            with self.assertRaisesRegex(RuntimeError, "inspect state"):
                CageDesktop.run(["wtype", "-"])
        self.assertEqual(run.call_count, 1)

    def test_launch_uses_literal_argv_and_unique_unit(self):
        desktop = CageDesktop()
        process = Mock(poll=Mock(return_value=None))
        def start(argv, **kwargs):
            kwargs["stdout"].write(b"Cage display: wayland-17\n")
            return process
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/tmp"}), \
             patch("shutil.which", return_value="/bin/test-app"), \
             patch("subprocess.Popen", side_effect=start) as spawn, \
             patch.object(desktop, "stop_process"):
            result = desktop.launch("test-app", ["a b", "$(touch never)"])
            argv = spawn.call_args.args[0]
            self.assertEqual(argv[-3:], ["/bin/test-app", "a b", "$(touch never)"])
            self.assertEqual(argv[argv.index("--name") + 1], result["id"])
            self.assertEqual(desktop.get(result["id"]).display, "wayland-17")
            desktop.close_all()

    def test_cli_help_and_unexpected_arguments_do_not_start_server(self):
        self.enterContext(patch.dict(os.environ, {"NO_COLOR": "1"}))
        with patch("cage_use.__main__.create_server") as server, \
             patch("sys.stdout", new_callable=StringIO) as output:
            with self.assertRaises(SystemExit) as stopped:
                main(["--help"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn("usage: cage-mcp", output.getvalue())
        server.assert_not_called()

        with patch("cage_use.__main__.create_server") as server, \
             patch("sys.stderr", new_callable=StringIO) as error:
            with self.assertRaises(SystemExit) as stopped:
                main(["unexpected"])
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("usage: cage-mcp", error.getvalue())
        server.assert_not_called()


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_apps_survive_mcp_reconnect_and_close_explicitly(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with fake_recorder(), tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worker.sock"
            desktop = FakeDesktop()
            with SessionService(path, desktop) as service:
                thread = threading.Thread(target=service.serve_forever)
                thread.start()
                try:
                    params = StdioServerParameters(command=sys.executable,
                        args=["-m", "cage_use", "--connect", str(path)], env=dict(os.environ))
                    with self.assertRaises(OSError):
                        SessionService(path, FakeDesktop())
                    self.assertTrue(path.exists())
                    async with stdio_client(params) as (reader, writer):
                        async with ClientSession(reader, writer) as client:
                            await client.initialize()
                            result = await client.call_tool("launch_app", {"executable": "test-app"})
                            self.assertFalse(result.isError)
                            await client.call_tool("get_app_state", {"app": "owned"})
                            started = await client.call_tool("start_recording", {"app": "owned"})
                            self.assertFalse(started.isError)
                            video = Path(json.loads(started.content[0].text)["path"])
                    self.assertIn("owned", desktop.sessions)
                    async with stdio_client(params) as (reader, writer):
                        async with ClientSession(reader, writer) as client:
                            await client.initialize()
                            apps = await client.call_tool("list_apps", {})
                            self.assertFalse(apps.isError)
                            self.assertIn("owned", str(apps))
                            self.assertIn("recording", str(apps))
                            drag = await client.call_tool("drag", {"app": "owned", "from_x": 1,
                                "from_y": 2, "to_x": 799, "to_y": 599})
                            self.assertFalse(drag.isError)
                            self.assertEqual(drag.content[1].type, "image")
                            recording = await client.call_tool("stop_recording", {"app": "owned"})
                            self.assertFalse(recording.isError)
                            details = json.loads(recording.content[0].text)
                            self.assertEqual(details["status"], "finished")
                            self.assertEqual(Path(details["path"]), video)
                            closed = await client.call_tool("close_app", {"app": "owned"})
                            self.assertFalse(closed.isError)
                    self.assertEqual(desktop.sessions, {})
                    self.assertTrue(video.exists())
                    ServiceDesktop(path).launch("test-app", [])
                finally:
                    service.shutdown()
                    thread.join()
            self.assertEqual(desktop.sessions, {})
            self.assertFalse(path.exists())

    async def test_service_rejects_unowned_or_public_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worker.sock"
            path.write_text("not a socket")
            with self.assertRaisesRegex(ValueError, "Unix socket"):
                ServiceDesktop(path)
            path.unlink()
            Path(directory).chmod(0o755)
            with self.assertRaisesRegex(ValueError, "private"):
                SessionService(path, FakeDesktop())

    async def test_stdio_images_errors_and_disconnect_cleanup(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "closed"
            params = StdioServerParameters(command="cage-mcp-test-server",
                                           env=dict(os.environ, CAGE_TEST_CLOSED=str(marker),
                                                    PYTHONDONTWRITEBYTECODE="1"))
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    self.assertEqual(set(tools), {"launch_app", "list_apps", "get_app_state", "click",
                                                   "drag", "scroll", "press_key", "type_text", "close_app",
                                                   "start_recording", "stop_recording"})
                    self.assertTrue(tools["get_app_state"].annotations.readOnlyHint)
                    self.assertFalse(tools["click"].annotations.readOnlyHint)
                    await client.call_tool("launch_app", {"executable": "test-app"})
                    state = await client.call_tool("get_app_state", {"app": "owned"})
                    self.assertFalse(state.isError)
                    self.assertEqual(state.structuredContent["screenshot"]["width"], 800)
                    self.assertEqual(state.content[1].type, "image")
                    self.assertEqual(state.content[1].mimeType, "image/png")
                    for args in [{"app": "other", "x": 1, "y": 2},
                                 {"app": "owned", "element_index": 1},
                                 {"app": "owned", "x": True, "y": 2},
                                 {"app": "owned", "x": 1, "y": 2, "click_count": 0}]:
                        result = await client.call_tool("click", args)
                        self.assertTrue(result.isError, args)
                    result = await client.call_tool("click", {"app": "owned", "x": 10, "y": 20})
                    self.assertFalse(result.isError)
                    self.assertEqual(result.content[1].type, "image")
            self.assertEqual(marker.read_text(), "closed")


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(fake_recorder())
        self.desktop = FakeDesktop()
        self.desktop.launch("test-app", [])
        self.addCleanup(self.desktop.close_all)

    def test_recording_stop_is_idempotent_and_video_survives_app_close(self):
        started = self.desktop.start_recording("owned")
        self.assertEqual(started["status"], "recording")
        self.assertEqual(started["mimeType"], "video/mp4")
        with self.assertRaisesRegex(ValueError, "already recording"):
            self.desktop.start_recording("owned")
        self.assertEqual(self.desktop.list_apps()[0]["recording"]["path"], started["path"])
        self.assertEqual(self.desktop.capture("owned")[0]["recording"]["status"], "recording")
        stopped = self.desktop.stop_recording("owned")
        self.assertEqual(stopped["status"], "finished")
        self.assertEqual(self.desktop.stop_recording("owned"), stopped)
        closed = self.desktop.close("owned")
        self.assertEqual(closed["recording"]["path"], stopped["path"])
        self.assertEqual(Path(stopped["path"]).read_bytes(), b"video-headerfinalized")

    def test_app_cleanup_finalizes_active_recording(self):
        started = self.desktop.start_recording("owned")
        process = self.desktop.sessions["owned"].recording.process
        self.desktop.close_all()
        self.assertEqual(process.poll(), 0)
        self.assertEqual(Path(started["path"]).read_bytes(), b"video-headerfinalized")

    def test_recording_requires_ownership_and_uses_app_display(self):
        with self.assertRaises(ValueError):
            self.desktop.start_recording("unowned")
        with self.assertRaises(ValueError):
            self.desktop.stop_recording("owned")
        from cage_use.recording import Recording
        with patch.object(Recording, "start", return_value=Mock(summary=Mock(return_value={}))) as start:
            self.desktop.start_recording("owned")
            self.assertEqual(start.call_args.args[1]["WAYLAND_DISPLAY"], "wayland-test")
            self.desktop.sessions["owned"].recording = None

    def test_recorder_startup_failure_does_not_leak_an_app_recording(self):
        (self.root / "wf-recorder").write_text(f"#!{sys.executable}\nimport sys\nsys.exit(1)\n")
        with self.assertRaisesRegex(RuntimeError, "startup"):
            self.desktop.start_recording("owned")
        self.assertIsNone(self.desktop.sessions["owned"].recording)
        self.assertEqual(list((self.root / "recordings").glob("*.mp4")), [])

    def test_finalize_timeout_kills_recorder_and_still_closes_other_apps(self):
        from cage_use.recording import Recording
        path = self.root / "unfinished.mp4"
        path.write_bytes(b"partial")
        log = self.root / "recorder.log"
        log.write_text("")
        process = Mock(poll=Mock(side_effect=[None, None, -9]),
                       wait=Mock(side_effect=[subprocess.TimeoutExpired("wf-recorder", 10), 0]))
        self.desktop.sessions["owned"].recording = Recording(process, path, log)
        self.desktop.sessions["other"] = Session("other", "test-app", 5906, "wayland-other",
            Mock(poll=Mock(return_value=None)), tempfile.TemporaryDirectory())
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            self.desktop.close_all()
        process.kill.assert_called_once()
        self.assertEqual(self.desktop.sessions, {})
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
