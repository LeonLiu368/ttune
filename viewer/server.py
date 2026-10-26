"""The viewer server: the static pages, the same data the static build writes, and an API to launch runs.

Endpoints:
  GET  /api/health        {"server": true, "launch": bool, ...}; the frontend turns the launch form on from this
  GET  /api/launches      the latest eval workflow runs on GitHub (when launching is set up)
  POST /api/runs          start an eval run (JSON body, see viewer/launch.py); needs X-Launch-Key if one is set
  GET  /data/...          run data, as described in viewer/data.py
  GET  /...               the frontend in viewer/static
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evals.local_model import presets
from viewer import data
from viewer.build import STATIC_DIR
from viewer.launch import GitHubLauncher, LaunchError, validate

MAX_BODY = 10_000
DATA_ROUTE = re.compile(r"^/data/runs/([^/]+)/(overview\.json|id\.json|ood\.json|cases/([^/]+)\.json)$")


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, *, results_dir: Path = data.RESULTS_DIR, sets_dir: Path = data.SETS_DIR,
                 launcher: GitHubLauncher | None = None, launch_key: str | None = None, allow_paid: bool = False):
        super().__init__(address, Handler)
        self.results_dir, self.sets_dir = results_dir, sets_dir
        self.launcher, self.launch_key, self.allow_paid = launcher, launch_key, allow_paid
        self._overviews: dict[str, tuple[tuple, dict]] = {}

    def overview(self, run_dir: Path) -> dict:
        """run_overview is slow (bootstrap intervals), so keep it until the run's files change."""
        stamp = tuple(p.stat().st_mtime_ns for p in sorted(run_dir.glob("*.json*")))
        cached = self._overviews.get(run_dir.name)
        if not cached or cached[0] != stamp:
            cached = (stamp, data.run_overview(run_dir))
            self._overviews[run_dir.name] = cached
        return cached[1]


class Handler(BaseHTTPRequestHandler):
    server: ViewerServer

    def log_message(self, fmt, *args):  # quieter than the default, still one line per request
        print(f"{self.address_string()} {fmt % args}")

    # --- responses ------------------------------------------------------------------------------

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _file(self, path: Path) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    # --- GET ------------------------------------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            launcher = self.server.launcher
            return self._json(200, {"server": True, "launch": launcher is not None,
                                    "allow_paid": self.server.allow_paid, "needs_key": bool(self.server.launch_key),
                                    "presets": sorted(presets()), "actions_url": launcher.actions_url if launcher else None})
        if path == "/api/launches":
            if not self.server.launcher:
                return self._error(404, "launching isn't set up on this server")
            try:
                return self._json(200, self.server.launcher.recent())
            except Exception as exc:  # GitHub down or token expired: say so, don't crash the page
                return self._error(502, f"couldn't list runs on GitHub: {exc}")
        if path == "/data/site.json":
            return self._json(200, {"static": False})
        if path == "/data/runs.json":
            return self._json(200, data.runs_index(self.server.results_dir))
        match = DATA_ROUTE.match(path)
        if match:
            return self._data(*match.groups())
        return self._static(path)

    def _data(self, run_id: str, name: str, case_id: str | None):
        run_dir = self.server.results_dir / run_id
        if not data.safe(run_id) or not (run_dir / "summary.json").is_file():
            return self._error(404, "no such run")
        if name == "overview.json":
            return self._json(200, self.server.overview(run_dir))
        if case_id is not None:
            detail = data.case_detail(run_dir, case_id, self.server.sets_dir) if data.safe(case_id) else None
            return self._json(200, detail) if detail else self._error(404, "no such case")
        return self._json(200, data.case_rows(run_dir, name.removesuffix(".json")))

    def _static(self, path: str):
        relative = path.lstrip("/") or "index.html"
        target = (STATIC_DIR / relative).resolve()
        if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
            return self._error(404, "not found")
        return self._file(target)

    # --- POST -----------------------------------------------------------------------------------

    def do_POST(self):
        if self.path != "/api/runs":
            return self._error(404, "not found")
        launcher = self.server.launcher
        if launcher is None:
            return self._error(503, "launching isn't set up on this server (no VIEWER_GITHUB_TOKEN)")
        key = self.server.launch_key
        if key and not hmac.compare_digest(self.headers.get("X-Launch-Key", ""), key):
            return self._error(403, "wrong or missing launch key")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY:
            return self._error(400, "send a JSON body")
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._error(400, "the body isn't a JSON object")
        try:
            workflow, inputs = validate(body, allow_paid=self.server.allow_paid)
            launcher.dispatch(workflow, inputs)
        except LaunchError as exc:
            return self._error(400, str(exc))
        return self._json(202, {"workflow": workflow, "inputs": inputs, "actions_url": launcher.actions_url})
