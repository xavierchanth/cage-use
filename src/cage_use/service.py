"""User-local session ownership independent of an MCP client's lifetime."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import stat

from .session import CageDesktop


MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
OPERATIONS = {"launch", "list_apps", "capture", "interact", "close", "start_recording", "stop_recording"}


def endpoint(path: str | Path, *, create: bool = False) -> Path:
    path = Path(path).absolute()
    if create:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        raise ValueError("The service socket needs an owned, private (0700) parent directory.")
    if not create:
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("The service endpoint must be an owned, private Unix socket.")
    return path


class SessionService(socketserver.ThreadingUnixStreamServer):
    # Wait for accepted requests before destroying their owned apps.
    daemon_threads = False

    def __init__(self, path: str | Path, desktop: CageDesktop | None = None):
        self.desktop = desktop or CageDesktop()
        self._bound = False
        path = endpoint(path, create=True)
        # Do not replace a live service or silently unlink an unknown socket.
        super().__init__(str(path), SessionRequest)

    def server_bind(self):
        super().server_bind()
        self._bound = True
        os.chmod(self.server_address, 0o600)

    def server_close(self):
        # Finish any active desktop operation before cleanup. New calls must
        # stop before the service closes, so shutdown precedes server_close.
        super().server_close()
        if self._bound:
            try:
                self.desktop.close_all()
            finally:
                Path(self.server_address).unlink(missing_ok=True)
                self._bound = False


class SessionRequest(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(60)
        try:
            line = self.rfile.readline(MAX_REQUEST_BYTES + 1)
            if len(line) > MAX_REQUEST_BYTES or not line.endswith(b"\n"):
                raise ValueError("Invalid or oversized service request.")
            request = json.loads(line)
            operation, args = request["operation"], request["args"]
            if operation not in OPERATIONS or not isinstance(args, list):
                raise ValueError("Unknown service operation or invalid arguments.")
            with self.server.desktop.lock:
                result = getattr(self.server.desktop, operation)(*args)
            if operation in {"capture", "interact"}:
                metadata, png = result
                result = [metadata, base64.b64encode(png).decode()]
            response = {"result": result}
        except Exception as error:
            response = {"error": str(error), "invalid": isinstance(error, ValueError)}
        try:
            self.wfile.write(json.dumps(response).encode() + b"\n")
        except (BrokenPipeError, ConnectionResetError):
            # Client loss never relinquishes the service's app ownership.
            pass


class ServiceDesktop:
    """MCP adapter for a running session service; transport failures aren't retried."""

    def __init__(self, path: str | Path):
        self.path = endpoint(path)

    def call(self, operation: str, *args):
        data = json.dumps({"operation": operation, "args": args}).encode() + b"\n"
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError("Service request exceeds the 1 MiB limit.")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(60)
                connection.connect(str(self.path))
                connection.sendall(data)
                with connection.makefile("rb") as reader:
                    line = reader.readline(MAX_RESPONSE_BYTES + 1)
            if len(line) > MAX_RESPONSE_BYTES or not line.endswith(b"\n"):
                raise RuntimeError("Invalid or oversized service response.")
            response = json.loads(line)
        except (OSError, ValueError) as error:
            raise RuntimeError("Session service unavailable; reconnect and inspect state before retrying.") from error
        if "error" in response:
            exception = ValueError if response.get("invalid") else RuntimeError
            raise exception(response["error"])
        result = response["result"]
        if operation in {"capture", "interact"}:
            return result[0], base64.b64decode(result[1], validate=True)
        return result

    def launch(self, executable, args):
        return self.call("launch", executable, args)

    def list_apps(self):
        return self.call("list_apps")

    def capture(self, app):
        return self.call("capture", app)

    def interact(self, operation, app, *args):
        return self.call("interact", operation, app, *args)

    def close(self, app):
        return self.call("close", app)

    def start_recording(self, app):
        return self.call("start_recording", app)

    def stop_recording(self, app):
        return self.call("stop_recording", app)


def serve(path: str | Path):
    def terminate(_signal, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        with SessionService(path) as service:
            try:
                service.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        signal.signal(signal.SIGTERM, previous)
