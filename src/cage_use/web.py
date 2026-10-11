"""Launch the locally packaged Node/noVNC browser gateway."""
import os
from pathlib import Path
import sys


def main(argv=None):
    root = Path(os.environ.get("CAGE_WEB_ROOT", Path(__file__).resolve().parents[2] / "web"))
    server = root / "server.mjs"
    if not server.is_file():
        raise SystemExit("Browser assets missing. Use the complete Nix package, or run bun install in web/ for development.")
    os.execvp("node", ["node", str(server), *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    main()
