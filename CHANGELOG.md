# Changelog

All notable changes to cage-use are documented here.

## 0.2.0 - 2026-09-21

- Ship `cage-mcp`, `cage-session`, and `cage-session-app` in one canonical Nix derivation with their complete runtime closure.
- Install the companion Codex skill at `share/codex/skills/cage-use/SKILL.md`.
- Install the README, MCP reference, changelog, and license under `share/doc/cage-use`.
- Export `cage-use`, `cage-mcp`, `cage-session`, `cage-session-app`, and `default` as aliases of the same derivation.
- Keep `nix/mcp-package.nix` as a compatibility import.
- Add a Nix packaging check for installed executables and resources.
- Add conventional help and argument validation for the exported commands.
