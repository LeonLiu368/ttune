"""Start eval runs from the viewer by dispatching the eval workflows on GitHub Actions.

The server only launches when it has a GitHub token (VIEWER_GITHUB_TOKEN, with permission to run Actions on the
repo). Inputs are checked here before anything is sent, and paid models stay refused unless the server was
started with VIEWER_ALLOW_PAID=1; the eval workflow's own cost guard still applies on top.
"""

from __future__ import annotations

import re

import httpx

from evals.local_model import presets

API = "https://api.github.com"
WORKFLOWS = {"self-hosted": "eval-local.yml", "openrouter": "eval.yml"}
MODEL_SLUG = re.compile(r"^(free|[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*(:[a-z0-9-]+)?)$")
REASONING = ("", "none", "minimal", "low", "medium", "high")


class LaunchError(ValueError):
    pass


def _int(body: dict, key: str, default: int, low: int, high: int) -> str:
    value = body.get(key, default)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise LaunchError(f"{key} must be a whole number") from None
    if not low <= number <= high:
        raise LaunchError(f"{key} must be between {low} and {high}")
    return str(number)


def _limit(body: dict) -> str:
    value = str(body.get("limit", "10")).strip().lower()
    return "all" if value in ("all", "", "0") else _int({"limit": value}, "limit", 10, 1, 200)


def validate(body: dict, allow_paid: bool = False) -> tuple[str, dict[str, str]]:
    """(workflow file, workflow inputs) for a launch request, or LaunchError saying what's wrong."""
    backend = body.get("backend")
    if backend not in WORKFLOWS:
        raise LaunchError(f"backend must be one of {sorted(WORKFLOWS)}")
    if backend == "self-hosted":
        preset = body.get("preset")
        if preset not in presets():
            raise LaunchError(f"preset must be one of {sorted(presets())}")
        inputs = {"preset": preset, "limit": _limit(body), "shards": _int(body, "shards", 1, 1, 20),
                  "max_tokens": _int(body, "max_tokens", 6000, 500, 16000)}
    else:
        model = str(body.get("model", "free")).strip()
        if not MODEL_SLUG.match(model):
            raise LaunchError("model must be an OpenRouter id like vendor/model or vendor/model:free, or \"free\"")
        paid = bool(body.get("allow_paid"))
        if paid and not allow_paid:
            raise LaunchError("paid models are switched off on this server (start it with VIEWER_ALLOW_PAID=1)")
        effort = str(body.get("reasoning_effort", "")).strip()
        if effort not in REASONING:
            raise LaunchError(f"reasoning_effort must be one of {list(REASONING)}")
        inputs = {"model": model, "limit": _limit(body), "allow_paid": "true" if paid else "false",
                  "max_tokens": _int(body, "max_tokens", 8000, 500, 16000), "reasoning_effort": effort}
    return WORKFLOWS[backend], inputs


class GitHubLauncher:
    def __init__(self, repo: str, token: str, ref: str = "main", client: httpx.Client | None = None):
        self.repo, self.ref = repo, ref
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"}

    def dispatch(self, workflow: str, inputs: dict[str, str]) -> None:
        url = f"{API}/repos/{self.repo}/actions/workflows/{workflow}/dispatches"
        resp = self.client.post(url, headers=self.headers, json={"ref": self.ref, "inputs": inputs})
        if resp.status_code not in (200, 204):
            raise LaunchError(f"GitHub refused the launch (HTTP {resp.status_code}): {resp.text[:300]}")

    def recent(self, limit: int = 10) -> list[dict]:
        """The latest eval workflow runs, newest first."""
        resp = self.client.get(f"{API}/repos/{self.repo}/actions/runs", headers=self.headers,
                               params={"per_page": 30, "event": "workflow_dispatch"})
        resp.raise_for_status()
        paths = {f".github/workflows/{w}" for w in WORKFLOWS.values()}
        runs = [r for r in resp.json().get("workflow_runs", []) if r.get("path") in paths]
        return [{"id": r["id"], "workflow": r.get("name"), "status": r.get("status"), "conclusion": r.get("conclusion"),
                 "created_at": r.get("created_at"), "url": r.get("html_url")} for r in runs[:limit]]

    @property
    def actions_url(self) -> str:
        return f"https://github.com/{self.repo}/actions"
