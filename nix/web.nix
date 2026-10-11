{ pkgs }:
let
  novnc = pkgs.fetchzip {
    url = "https://registry.npmjs.org/@novnc/novnc/-/novnc-1.7.0.tgz";
    hash = "sha256-0adUCvVo5Bwi2OPF5QdZxS+UbCsz46LiNhqxBuiSwqk=";
  };
  ws = pkgs.fetchzip {
    url = "https://registry.npmjs.org/ws/-/ws-8.22.0.tgz";
    hash = "sha256-NsBRErrxWcqva2Ecm9YoOSLj0HUbqIkbeoIKfG0LkWY=";
  };
in pkgs.runCommand "cage-web-assets" { } ''
  mkdir -p "$out/node_modules/@novnc"
  cp ${../web/server.mjs} "$out/server.mjs"
  cp ${../web/viewer.html} "$out/viewer.html"
  cp ${../web/viewer.js} "$out/viewer.js"
  cp ${../web/test.mjs} "$out/test.mjs"
  ln -s ${novnc} "$out/node_modules/@novnc/novnc"
  ln -s ${ws} "$out/node_modules/ws"
''
