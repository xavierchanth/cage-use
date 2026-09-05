"""Fake Cage runtime shared with the stdio subprocess test."""

from io import BytesIO
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock

from cage_use.session import CageDesktop, Session
from PIL import Image


def png_bytes():
    output = BytesIO()
    Image.new("RGB", (800, 600), "white").save(output, "PNG")
    return output.getvalue()


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
