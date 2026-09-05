{ pkgs }:

pkgs.python3Packages.buildPythonApplication {
  pname = "cage-use";
  version = "0.1.0";
  pyproject = true;
  src = ../.;
  build-system = [ pkgs.python3Packages.setuptools ];
  dependencies = with pkgs.python3Packages; [ mcp pillow ];
  nativeBuildInputs = [ pkgs.makeWrapper ];
  postFixup = ''
    wrapProgram "$out/bin/cage-mcp" \
      --prefix PATH : ${pkgs.lib.makeBinPath [
        (import ./package.nix { inherit pkgs; })
        pkgs.grim pkgs.wtype pkgs.python3Packages.vncdotool pkgs.systemd
      ]}
  '';
  meta.mainProgram = "cage-mcp";
}
