# MCP interface

`cage-mcp` is the v0 delivery interface for cage-use. It exposes app-scoped computer use over MCP stdio. Cage is the sole runtime target. The complete Nix package also provides both session launchers and installs this reference, the project documentation and license, and the companion Codex skill.

## Interface

The installed macOS Computer Use plugin's `computer-use` skill documents a
`Sky` interface backed by `@oai/sky`; the newer unified plugin wraps that service
in a JavaScript REPL. This server follows the documented app-scoped method names
and input conventions, using ordinary MCP tools rather than reproducing that
private REPL service.

| Tool | Cage behavior |
| --- | --- |
| `launch_app(executable, args)` | Create a new task-specific session; return its opaque app ID. |
| `list_apps()` | List sessions owned by this connection or its connected session service. |
| `get_app_state(app, disableDiff)` | Return a full PNG image and dimensions; `disableDiff` is accepted without changing behavior. |
| `click(app, x, y, mouse_button, click_count)` | Move and click within the session using one VNC connection. |
| `drag(app, from_x, from_y, to_x, to_y)` | Drag with the left mouse button using at most 20 motion steps and 420 ms of explicit pauses. |
| `scroll(app, direction, x, y, pages)` | Scroll at the given location; a page approximates eight wheel steps. |
| `press_key(app, key)` | Send an XKB key or chord such as `Return` or `ctrl+a`. |
| `type_text(app, text)` | Type UTF-8 text; newline characters can submit forms. |
| `close_app(app)` | Stop the owned systemd scope and clean up temporary session files. |
| `start_recording(app)` | Start a silent 30 fps H.264 MP4 of the app's full Cage display. |
| `stop_recording(app)` | Finalize the video and return its host-local path and size. |

An `app` is a session ID returned by this server, not a macOS bundle identifier,
process ID, arbitrary Wayland socket, or TCP endpoint. `get_app_state` does not
implicitly launch an app. Each owner (stdio process or session service) is limited
to four sessions.

State results contain native MCP `image` content (`image/png`, base64) plus
structured metadata: app ID, backend, screenshot width/height, original-pixel
coordinate space, and supported capabilities. Images are not resized. There is
no host-local `file://` URL for clients to retrieve across SSH. Input tools return
a fresh screenshot so the client can inspect the result before acting again.

The macOS accessibility tree, diffs, `element_index`, `set_value`, `select_text`,
`perform_secondary_action`, and rich `paste` semantics are not implemented.
Coordinate actions require a previous screenshot and reject out-of-bounds
coordinates. `element_index` requests explicitly fail. This is a compatible
subset of interaction concepts, not a drop-in `@oai/sky` replacement or the
built-in Codex Computer Use plugin.

## Transport and ownership

Codex launches the server locally on the selected host. A client on another
machine can also launch `cage-mcp` via its authorized SSH command as a stdio MCP
server. SSH diagnostics must stay on stderr; do not allocate a TTY for MCP.
No HTTP endpoint or additional firewall opening is configured.

Each session has its own random systemd scope name. The server never attaches
to an existing desktop or accepts a caller-selected port. Plain stdio mode stops
owned scopes on `close_app`, startup failure, or MCP disconnect. Unique scope names prevent
cleanup from targeting an unrelated app that later reuses a VNC port.

### Persistent sessions

Optional service mode separates app ownership from MCP transport:

- `cage-mcp --serve SOCKET` owns apps and serves a private Unix socket.
- `cage-mcp --connect SOCKET` exposes the same MCP stdio tools as a service client.
- Reconnecting to the same service preserves app IDs. Call `list_apps`, then
  `get_app_state` before continuing. `close_app` explicitly ends an app.
- Stopping the service closes all its apps and removes its socket. Service
  crashes or host reboots are not recoverable sessions; a stale socket must
  be removed before restarting after a crash.

The socket parent must belong to the current user and have mode `0700`; the
socket has mode `0600`. All clients of one service share its apps and four-app
limit. Use separate sockets for tasks that need independent ownership. An
input action and its resulting screenshot are serialized together. Transport
errors are never retried automatically because the action may already have
completed.

For a persistent systemd user service, install this unit as
`~/.config/systemd/user/cage-use.service`, replacing the executable path with
the installed package's absolute path:

```ini
[Unit]
Description=Cage app session service

[Service]
Type=simple
RuntimeDirectory=cage-use
RuntimeDirectoryMode=0700
ExecStart=/absolute/path/to/bin/cage-mcp --serve %t/cage-use/worker.sock

[Install]
WantedBy=default.target
```

Run `systemctl --user daemon-reload` and
`systemctl --user enable --now cage-use.service`. The host's user-service
lingering setting must allow the user manager to survive logout. Then
configure the remote MCP command as:

```sh
ssh -T HOST /absolute/path/to/bin/cage-mcp --connect /run/user/UID/cage-use/worker.sock
```

Use the target user's actual runtime path. Each stdio client maintains its
SSH process while connected; SSH ControlMaster reuse is independent of the
session service. Service mode does not expose a network listener.

### Screen recording

Call `start_recording(app)`, interact with the app, then call
`stop_recording(app)`. Each app can have one active recording. `list_apps`
and `get_app_state` include its recording status and path. Stopping again
returns the same completed recording; starting again creates a new file.

Videos are saved under `$XDG_STATE_HOME/cage-use/recordings` (default
`~/.local/state/cage-use/recordings`). Set `CAGE_USE_RECORDING_DIR` on the
owning MCP process or session service to choose another directory. The
directory must be owned by the user with mode `0700`; files have mode `0600`.
Files survive app and service cleanup and are retained until explicitly
removed by the user. The recording captures only the owned Cage display,
including the pointer, without audio.

`close_app`, plain stdio disconnect, and graceful service shutdown finalize
active videos before closing their displays. Service-owned recordings
continue through MCP/SSH reconnects. Abrupt termination may leave an
incomplete MP4.

The returned file path belongs to the host running Cage. For remote
sessions, copy the finalized video over SSH, for example:

```sh
scp HOST:/absolute/path/from/stop_recording.mp4 ./recording.mp4
```

Recording uses `wf-recorder` with software H.264 encoding, shared-memory
capture, and continuous frame capture to support headless software-rendered
Cage sessions. The Nix package includes the recorder.

WayVNC listens on loopback; screenshots use `grim`, pointer actions use `vncdo`,
and keyboard actions use `wtype`. Text travels over stdin instead of becoming
shell syntax. The server, sessions, and applications run as the user who invokes
`cage-mcp`. Cage is a display boundary, not an OS sandbox: launching an
executable grants it that user's filesystem and network access.

## Validation and sources

`tests/cage-mcp.py` exercises the Cage session boundaries and a real MCP stdio
initialize/list/call/disconnect exchange with a fake display. The Nix flake
exposes it as `checks.SYSTEM.protocol`. `tests/cage-session.py` tests
the launcher lifecycle. `checks.SYSTEM.packaging` verifies that the complete
derivation contains all three executables and installed resources. These tests
do not replace a live Wayland smoke test.

Interface reference: installed OpenAI `computer-use` plugin version
`1.0.1000926`, `skills/computer-use/SKILL.md` (`Sky` API), and unified plugin
version `26.901.41600`, its launcher and tool descriptions. No private native
implementation is copied or required.

- [MCP Python SDK v1](https://py.sdk.modelcontextprotocol.io/v1/) — the pinned Nixpkgs provides SDK 1.29.0.
- [WayVNC](https://github.com/any1/wayvnc) — headless Wayland capture and input.
- [VNCDoTool commands](https://vncdotool.readthedocs.io/en/latest/usage.html) — pointer operations.
- [wtype](https://github.com/atx/wtype) — Wayland keyboard input.
- [wf-recorder](https://github.com/ammen99/wf-recorder) — Wayland screen recording.
