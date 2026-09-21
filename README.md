# cage-use

App-scoped computer use for Linux, backed by headless Cage sessions.

cage-use launches a task-specific application, captures its display, sends pointer and keyboard input, and cleans up the session when finished. Cage is the sole runtime. MCP is the v0 delivery interface, accompanied by a Codex skill; the session layer remains independent of MCP so another delivery can be added separately.

## Status

Version 0.2.0 provides one complete Nix package containing the MCP server, session launchers, Codex skill, documentation, and runtime dependencies. Launcher and MCP contract tests use fake displays; a live Wayland smoke test is still pending.

## Layout

- `src/cage_use/`: installed Python package, with MCP-independent session behavior and the MCP v0 adapter.
- `scripts/`: Cage shell launchers that form the runtime process boundary.
- `skills/cage-use/`: companion Codex skill included in the Nix package.
- `nix/`: the canonical complete-package derivation and its compatibility import.
- `tests/`: lifecycle tests and MCP protocol tests.
- `docs/mcp.md`: current tool contract and implementation limits.

Session ownership, screen capture, and input behavior live in `cage_use.session`. MCP tool schemas and response encoding live in `cage_use.mcp`.

## Nix

On Linux, build with `nix build .#cage-use` and run checks with `nix flake check`. The default package and the `cage-use`, `cage-mcp`, `cage-session`, and `cage-session-app` package outputs are aliases of the same complete derivation.

Install the immutable v0.2.0 release into a Nix profile with:

```console
nix profile install github:xavierchanth/cage-use/v0.2.0#cage-use
```

The result contains:

- `bin/cage-mcp`, the stdio MCP server;
- `bin/cage-session` and `bin/cage-session-app`, the session launchers;
- `share/codex/skills/cage-use/SKILL.md`, the companion Codex skill;
- `share/doc/cage-use`, the README, MCP reference, changelog, and license.

Register the server using `codex mcp add cage-use -- /absolute/path/to/result/bin/cage-mcp`. Install or link `result/share/codex/skills/cage-use` into the target host's Codex skills directory. A running systemd user manager and owned `XDG_RUNTIME_DIR` are required.

Host configuration remains responsible for selecting a machine, installing the package, registering the MCP server, and activating the skill.

Cage provides a separate display. Sessions and their applications run as the user who invokes `cage-mcp`, retaining that user's filesystem and network permissions.

## License

MIT. See [LICENSE](LICENSE).
