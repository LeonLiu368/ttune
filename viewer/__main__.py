"""python -m viewer build [--out _site] | python -m viewer serve [--host 127.0.0.1] [--port 8000]

Launching runs from `serve` is off unless VIEWER_GITHUB_TOKEN is set (a token allowed to run Actions on the repo).
Other settings: VIEWER_REPO (default LeonLiu368/ttune), VIEWER_LAUNCH_KEY (required when listening beyond this
machine), VIEWER_ALLOW_PAID=1 (allow paid OpenRouter models).
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from pathlib import Path

from viewer import data


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m viewer", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write the static site")
    b.add_argument("--out", type=Path, default=Path("_site"))
    b.add_argument("--results-dir", type=Path, default=data.RESULTS_DIR)
    s = sub.add_parser("serve", help="serve the viewer and the launch API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--results-dir", type=Path, default=data.RESULTS_DIR)
    args = parser.parse_args(argv)

    if args.command == "build":
        from viewer.build import build
        result = build(args.out, args.results_dir)
        print(f"wrote {result['runs']} runs and {result['cases']} cases to {result['out']}")
        return 0

    from viewer.launch import GitHubLauncher
    from viewer.server import ViewerServer
    token = os.environ.get("VIEWER_GITHUB_TOKEN")
    key = os.environ.get("VIEWER_LAUNCH_KEY") or None
    if token and not key and not _loopback(args.host):
        print("error: set VIEWER_LAUNCH_KEY before serving the launch API beyond this machine", file=sys.stderr)
        return 2
    launcher = GitHubLauncher(os.environ.get("VIEWER_REPO", "LeonLiu368/ttune"), token) if token else None
    server = ViewerServer((args.host, args.port), results_dir=args.results_dir, launcher=launcher, launch_key=key,
                          allow_paid=os.environ.get("VIEWER_ALLOW_PAID") == "1")
    print(f"viewer on http://{args.host}:{server.server_address[1]}/ "
          f"(launching {'on' if launcher else 'off: no VIEWER_GITHUB_TOKEN'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
