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
          cage-session = import ./nix/package.nix { inherit pkgs; };
          cage-mcp = import ./nix/mcp-package.nix { inherit pkgs; };
          default = cage-mcp;
        });
      checks = eachSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };
          mcpPackage = import ./nix/mcp-package.nix { inherit pkgs; };
        in {
          protocol = pkgs.runCommand "cage-use-protocol-tests" {
            nativeBuildInputs = [ mcpPackage pkgs.makeWrapper ];
            PYTHONDONTWRITEBYTECODE = "1";
          } ''
            makeWrapper ${./tests/cage-mcp-test-server} "$TMPDIR/bin/cage-mcp-test-server" \
              --prefix PATH : ${pkgs.lib.makeBinPath [ mcpPackage ]} \
              --prefix PYTHONPATH : ${./tests}
            export PATH="$TMPDIR/bin:$PATH"
            python3 ${./tests/cage-mcp.py}
            test -x ${mcpPackage}/bin/cage-mcp
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
        });
    };
}
