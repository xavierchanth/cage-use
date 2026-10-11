# cage-use

App-scoped computer use for Linux, backed by headless Cage sessions.

cage-use launches a task-specific application, captures its display, records videos, sends pointer and keyboard input, and cleans up the session when finished. Cage is the sole runtime. MCP is the v0 delivery interface, accompanied by a Codex skill; the session layer remains independent of MCP so another delivery can be added separately.

## Status

Version 0.4.0 adds a realtime browser viewer for service-owned apps, with locally served noVNC, private access links, Tailscale binding, and optional HTTPS. The complete Nix package includes the viewer and updated Codex skill. Nix checks cover session behavior, MCP, HTTP/WebSocket boundaries, HTTPS, and packaging. Live Firefox checks on Zeus verified browser input, form submission, reconnect, and reload over Tailscale.

## Layout

- `src/cage_use/`: installed Python package, with MCP-independent session behavior and the MCP v0 adapter.
- `web/`: Node WebSocket gateway and locally served noVNC browser client.
- `scripts/`: Cage shell launchers that form the runtime process boundary.
- `skills/cage-use/`: companion Codex skill included in the Nix package.
- `nix/`: the canonical complete-package derivation and its compatibility import.
- `tests/`: lifecycle, MCP protocol, and browser delivery tests.
- `docs/mcp.md`: current tool contract and implementation limits.
- `docs/browser.md`: browser controls and remote access setup.

Session ownership, screen capture, and input behavior live in `cage_use.session`. MCP tool schemas and response encoding live in `cage_use.mcp`.

## Nix

On Linux, build with `nix build .#cage-use` and run checks with `nix flake check`. The default package and the `cage-use`, `cage-mcp`, `cage-web`, `cage-session`, and `cage-session-app` package outputs are aliases of the same complete derivation.

Install the immutable v0.4.0 release into a Nix profile with:

```console
nix profile install github:xavierchanth/cage-use/v0.4.0#cage-use
```

The result contains:

- `bin/cage-mcp`, the stdio MCP server;
- `bin/cage-web`, the browser viewer for persistent apps;
- `bin/cage-session` and `bin/cage-session-app`, the session launchers;
- `share/codex/skills/cage-use/SKILL.md`, the companion Codex skill;
- `share/doc/cage-use`, the README, MCP reference, changelog, and license.

Register the server using `codex mcp add cage-use -- /absolute/path/to/result/bin/cage-mcp`. Install or link `result/share/codex/skills/cage-use` into the target host's Codex skills directory. A running systemd user manager and owned `XDG_RUNTIME_DIR` are required.

Host configuration remains responsible for selecting a machine, installing the package, registering the MCP server, and activating the skill.

For apps that survive SSH or MCP reconnects, run `cage-mcp --serve SOCKET` as
a persistent user service and register `cage-mcp --connect SOCKET` as the MCP
command. The socket must live in an owned, private directory. See the
[service setup](docs/mcp.md#persistent-sessions) for a systemd example.
Plain `cage-mcp` continues to close its apps on disconnect.

To sign in or interact with the agent's apps yourself, run
`cage-web --connect SOCKET` with that same service socket and open its printed
private link. Add `--tailscale` to connect directly from another tailnet device.
For SSH access to a remote Cage host, forward port 6080 with
`ssh -N -L 6080:127.0.0.1:6080 HOST` and open the link locally. See
[browser access](docs/browser.md) for controls and setup. Closing the viewer
leaves the apps available to the agent.

Use `start_recording(app)` and `stop_recording(app)` to save a silent MP4 of
an app session. Videos survive app cleanup and default to
`~/.local/state/cage-use/recordings` on the Cage host. See
[screen recording](docs/mcp.md#screen-recording) for storage and remote downloads.

Cage provides a separate display. Sessions and their applications run as the user who invokes `cage-mcp`, retaining that user's filesystem and network permissions.

## License

MIT. See [LICENSE](LICENSE).
