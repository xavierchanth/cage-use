# Changelog

All notable changes to cage-use are documented here.

## Unreleased

## 0.3.0 - 2026-10-09

- Bound drag motion to 20 steps so long gestures fit within the command timeout.
- Add an optional private Unix-socket session service and MCP client mode so
  apps survive SSH/MCP reconnects until explicitly closed or the service stops.
- Serialize each input action with its resulting screenshot across service clients.
- Use explicit interpreter paths in the test harness so checks run in Nix sandboxes.
- Add app-scoped MP4 recording with start/stop tools, recording state across
  reconnects, graceful finalization on cleanup, and durable output files.
- Include `wf-recorder` in the complete Nix runtime package.

## 0.2.0 - 2026-09-21

- Ship `cage-mcp`, `cage-session`, and `cage-session-app` in one canonical Nix derivation with their complete runtime closure.
- Install the companion Codex skill at `share/codex/skills/cage-use/SKILL.md`.
- Install the README, MCP reference, changelog, and license under `share/doc/cage-use`.
- Export `cage-use`, `cage-mcp`, `cage-session`, `cage-session-app`, and `default` as aliases of the same derivation.
- Keep `nix/mcp-package.nix` as a compatibility import.
- Add a Nix packaging check for installed executables and resources.
- Add conventional help and argument validation for the exported commands.
