{
  description = "cage-use: app-scoped computer use for Linux";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/afb4584a80bbf779ce0f691509ff902d188c2b3d";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in {
      packages = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; }; in rec {
          cage-use = import ./nix/package.nix { inherit pkgs; };
          cage-mcp = cage-use;
          cage-session = cage-use;
          cage-session-app = cage-use;
          default = cage-use;
        });
      checks = eachSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };
          package = import ./nix/package.nix { inherit pkgs; };
          aliases = self.packages.${system};
          aliasesMatch = builtins.all
            (candidate: candidate.drvPath == package.drvPath)
            [ aliases.default aliases.cage-use aliases.cage-mcp
              aliases.cage-session aliases.cage-session-app ];
        in {
          protocol = pkgs.runCommand "cage-use-protocol-tests" {
            nativeBuildInputs = [ package pkgs.makeWrapper ];
            PYTHONDONTWRITEBYTECODE = "1";
          } ''
            makeWrapper ${./tests/cage-mcp-test-server} "$TMPDIR/bin/cage-mcp-test-server" \
              --prefix PATH : ${pkgs.lib.makeBinPath [ package ]} \
              --prefix PYTHONPATH : ${./tests}
            export PATH="$TMPDIR/bin:$PATH"
            python3 ${./tests/cage-mcp.py}
            test -x ${package}/bin/cage-mcp
            touch "$out"
          '';
          session = pkgs.runCommand "cage-use-session-tests" {
            nativeBuildInputs = [ pkgs.bash pkgs.python3 pkgs.shellcheck ];
            TEST_ROOT = self;
            TEST_BASH = "${pkgs.bash}/bin/bash";
          } ''
            shellcheck ${./scripts/cage-session.sh} ${./scripts/cage-session-app.sh}
            python3 ${./tests/cage-session.py}
            touch "$out"
          '';
          packaging = assert pkgs.lib.assertMsg aliasesMatch
            "all cage-use package outputs must resolve to the same derivation";
            pkgs.runCommand "cage-use-packaging-tests" { } ''
            test -x ${package}/bin/cage-mcp
            test -x ${package}/bin/cage-session
            test -x ${package}/bin/cage-session-app
            test -f ${package}/share/codex/skills/cage-use/SKILL.md
            test -f ${package}/share/doc/cage-use/README.md
            test -f ${package}/share/doc/cage-use/CHANGELOG.md
            test -f ${package}/share/doc/cage-use/mcp.md
            test -f ${package}/share/doc/cage-use/LICENSE
            touch "$out"
          '';
        });
    };
}
