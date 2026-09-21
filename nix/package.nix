{ pkgs }:
let
  project = builtins.fromTOML (builtins.readFile ../pyproject.toml);
  mcp = pkgs.python3Packages.mcp;
  supportedMcp =
    pkgs.lib.versionAtLeast mcp.version "1.29"
    && pkgs.lib.versionOlder mcp.version "2";
in
assert pkgs.lib.assertMsg supportedMcp
  "cage-use requires the MCP Python SDK >=1.29 and <2; nixpkgs provides ${mcp.version}";
pkgs.python3Packages.buildPythonApplication {
  pname = "cage-use";
  inherit (project.project) version;
  pyproject = true;
  src = ../.;
  build-system = [ pkgs.python3Packages.setuptools ];
  dependencies = [ mcp pkgs.python3Packages.pillow ];
  nativeBuildInputs = [ pkgs.makeWrapper ];

  postInstall = ''
    install -Dm755 scripts/cage-session.sh "$out/bin/cage-session"
    install -Dm755 scripts/cage-session-app.sh "$out/bin/cage-session-app"

    install -Dm644 skills/cage-use/SKILL.md \
      "$out/share/codex/skills/cage-use/SKILL.md"

    install -Dm644 README.md "$out/share/doc/cage-use/README.md"
    install -Dm644 CHANGELOG.md "$out/share/doc/cage-use/CHANGELOG.md"
    install -Dm644 docs/mcp.md "$out/share/doc/cage-use/mcp.md"
    install -Dm644 LICENSE "$out/share/doc/cage-use/LICENSE"
  '';

  postFixup = ''
    wrapProgram "$out/bin/cage-mcp" \
      --prefix PATH : ${pkgs.lib.makeBinPath [
        pkgs.grim pkgs.wtype pkgs.python3Packages.vncdotool pkgs.systemd
        pkgs.coreutils pkgs.dbus pkgs.cage pkgs.wayvnc
      ]} \
      --prefix PATH : "$out/bin"
    wrapProgram "$out/bin/cage-session" \
      --prefix PATH : ${pkgs.lib.makeBinPath [
        pkgs.coreutils pkgs.systemd pkgs.dbus pkgs.cage
      ]} \
      --prefix PATH : "$out/bin"
    wrapProgram "$out/bin/cage-session-app" \
      --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.coreutils pkgs.wayvnc ]}
  '';

  meta = {
    description = "App-scoped computer use through headless Cage sessions";
    homepage = "https://github.com/xavierchanth/cage-use";
    license = pkgs.lib.licenses.mit;
    mainProgram = "cage-mcp";
    platforms = pkgs.lib.platforms.linux;
  };
}
