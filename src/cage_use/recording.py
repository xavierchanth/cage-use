"""Capture one owned Wayland display to a durable video file."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time


@dataclass
class Recording:
    process: subprocess.Popen
    path: Path
    log: Path

    def summary(self) -> dict:
        code = self.process.poll()
        status = "recording" if code is None else "finished" if code == 0 else "failed"
        return {"path": str(self.path), "mimeType": "video/mp4", "status": status,
                "bytes": self.path.stat().st_size if self.path.exists() else 0,
                "fps": 30, "audio": False}

    def stop(self) -> dict:
        if self.process.poll() is None:
            try:
                self.process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired as error:
                self.process.kill()
                self.process.wait(timeout=3)
                raise RuntimeError(f"Recording did not finalize; video may be incomplete: {self.path}") from error
        result = self.summary()
        if result["status"] != "finished" or not result["bytes"]:
            detail = self.log.read_text(errors="replace")[-1000:]
            raise RuntimeError(f"Recording failed: {detail}; output: {self.path}")
        return result

    @classmethod
    def start(cls, app: str, environment: dict, session_directory: str) -> Recording:
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        directory = Path(os.environ.get("CAGE_USE_RECORDING_DIR", state / "cage-use/recordings")).absolute()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Recordings need an owned, private (0700) directory.")
        descriptor, filename = tempfile.mkstemp(prefix=f"{app}-", suffix=".mp4", dir=directory)
        os.close(descriptor)
        path = Path(filename)
        log = Path(session_directory) / f"{path.stem}.log"
        recording = None
        try:
            with log.open("wb") as output:
                process = subprocess.Popen(
                    ["wf-recorder", "--file", str(path), "--overwrite", "--codec", "libx264",
                     "--codec-param", "preset=ultrafast", "--pixel-format", "yuv420p",
                     "--filter", "scale=in_range=full:out_range=full",
                     "--framerate", "30", "--no-dmabuf", "--no-damage"],
                    env=environment, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                    start_new_session=True)
            recording = cls(process, path, log)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("wf-recorder exited during startup: " + log.read_text(errors="replace")[-1000:])
                if path.stat().st_size > 0:
                    return recording
                time.sleep(0.05)
            raise RuntimeError("wf-recorder startup timed out.")
        except BaseException:
            if recording is not None:
                try:
                    recording.stop()
                except RuntimeError:
                    pass
            path.unlink(missing_ok=True)
            raise
