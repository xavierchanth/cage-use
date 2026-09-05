# cage-use

App-scoped computer use for Linux, backed by headless Cage sessions.

cage-use launches a task-specific application, captures its display, sends pointer and keyboard input, and cleans up the session when finished. Cage is the sole runtime. MCP is the v0 delivery interface, accompanied by a Codex skill; the session layer remains independent of MCP so another delivery can be added separately.

## Status

Prototype extracted from the homelab dotfiles. Launcher and MCP contract tests use fake displays; a live Wayland smoke test is still pending. Nothing has been deployed by this extraction.

## Layout

- `src/cage_use/`: installed Python package, with MCP-independent session behavior and the MCP v0 adapter.
- `scripts/`: Cage shell launchers that form the runtime process boundary.
- `skills/cage-use/`: companion skill, installed only on hosts offering this capability.
- `nix/`: reproducible launcher and MCP packages.
- `tests/`: lifecycle tests and MCP protocol tests.
- `docs/mcp.md`: current tool contract and implementation limits.

Session ownership, screen capture, and input behavior live in `cage_use.session`. MCP tool schemas and response encoding live in `cage_use.mcp`.

## Nix

On Linux, build with `nix build .#cage-mcp`; run checks with `nix flake check`. The default package is the MCP server. The launcher is also exported as `cage-session`.

Register the built server using `codex mcp add cage-use -- /absolute/path/to/result/bin/cage-mcp`. Install `skills/cage-use` into the target host's Codex skills directory. A running systemd user manager and owned `XDG_RUNTIME_DIR` are required.

The homelab repository remains responsible for host selection, Codex installation, and activation. Its current prototype copy remains in place until a portable project source can be pinned; this project has no published remote yet.

Cage provides a separate display. Sessions and their applications run as the user who invokes `cage-mcp`, retaining that user's filesystem and network permissions.

## License

MIT. See [LICENSE](LICENSE).
