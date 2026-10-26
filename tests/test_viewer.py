"""Eval viewer: static build, data, server endpoints and launching. No network: GitHub is mocked."""

import http.client
import json
import shutil
import threading
from pathlib import Path

import httpx
import pytest

from viewer import data
from viewer.build import build
from viewer.launch import GitHubLauncher, LaunchError, validate
from viewer.server import ViewerServer

ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = next(p for p in sorted((ROOT / "evals" / "results").iterdir()) if (p / "summary.json").is_file())


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """A small copy of a real run: the first 6 households of each set."""
    root = tmp_path_factory.mktemp("results")
    run = root / "20991231-2359-local-test-model"
    run.mkdir()
    shutil.copy(REAL_RUN / "summary.json", run / "summary.json")
    for set_ in ("id", "ood"):
        lines = (REAL_RUN / f"{set_}.jsonl").read_text().splitlines()[:6]
        (run / f"{set_}.jsonl").write_text("\n".join(lines) + "\n")
    return root


def test_static_build_writes_every_page_the_frontend_reads(results, tmp_path):
    out = tmp_path / "site"
    summary = build(out, results)
    assert summary == {"runs": 1, "cases": 12, "out": str(out)}
    assert {p.name for p in out.iterdir()} >= {"index.html", "app.js", "style.css", "data", ".nojekyll"}
    assert json.loads((out / "data" / "site.json").read_text()) == {"static": True}
    runs = json.loads((out / "data" / "runs.json").read_text())
    assert runs[0]["run_id"] == "20991231-2359-local-test-model" and runs[0]["sets"]["id"]["n"] == 6
    base = out / "data" / "runs" / runs[0]["run_id"]
    overview = json.loads((base / "overview.json").read_text())
    assert {"settings", "sets", "headline", "changes", "families", "twists", "programs"} <= set(overview)
    assert overview["families"][0]["key"] == "id"
    rows = json.loads((base / "ood.json").read_text())
    assert [r["id"] for r in rows] == [f"ood-1-{i:04d}" for i in range(6)]
    case = json.loads((base / "cases" / "ood-1-0001.json").read_text())
    assert case["case"].startswith("Case ood-1-0001") and case["truth"]["snap"]["eligible"] in (True, False)
    assert case["members"] and {"id", "name", "age", "relationship"} == set(case["members"][0])


def test_ids_from_urls_must_be_plain_names():
    assert data.safe("20261026-0340-local-qwen3-4b-instruct") and data.safe("ood-1-0001")
    for bad in ("..", "../etc", "a/b", ".hidden", "", "x..y"):
        assert not data.safe(bad)


class FakeLauncher:
    actions_url = "https://github.com/example/ttune/actions"

    def __init__(self):
        self.dispatched = []

    def dispatch(self, workflow, inputs):
        self.dispatched.append((workflow, inputs))

    def recent(self, limit=10):
        return [{"id": 1, "workflow": "Eval (self-hosted model)", "status": "completed", "conclusion": "success"}]


@pytest.fixture()
def server(results):
    launcher = FakeLauncher()
    srv = ViewerServer(("127.0.0.1", 0), results_dir=results, launcher=launcher, launch_key="secret")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, launcher
    srv.shutdown()


def call(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json", **(headers or {})})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except ValueError:
        return resp.status, raw


def test_server_serves_pages_data_and_health(server):
    srv, _ = server
    status, health = call(srv, "GET", "/api/health")
    assert status == 200 and health["launch"] and health["needs_key"] and not health["allow_paid"]
    assert "qwen3-4b-instruct" in health["presets"]
    assert call(srv, "GET", "/data/site.json") == (200, {"static": False})
    status, runs = call(srv, "GET", "/data/runs.json")
    run_id = runs[0]["run_id"]
    assert call(srv, "GET", f"/data/runs/{run_id}/overview.json")[1]["run_id"] == run_id
    assert len(call(srv, "GET", f"/data/runs/{run_id}/id.json")[1]) == 6
    assert call(srv, "GET", f"/data/runs/{run_id}/cases/id-1-0002.json")[1]["id"] == "id-1-0002"
    assert call(srv, "GET", f"/data/runs/{run_id}/cases/id-1-0199.json")[0] == 404  # not in this small run
    assert call(srv, "GET", "/data/runs/nope/overview.json")[0] == 404
    status, page = call(srv, "GET", "/")
    assert status == 200 and b"ttune evals" in page
    assert call(srv, "GET", "/api/launches")[1][0]["conclusion"] == "success"


@pytest.mark.parametrize("path", ["/../README.md", "/%2e%2e/README.md", "/data/runs/../summary.json/overview.json",
                                  "/data/runs/x/cases/..%2f..%2fsecret.json"])
def test_server_refuses_paths_outside_its_files(server, path):
    assert call(server[0], "GET", path)[0] == 404


def test_launch_needs_the_key_and_valid_inputs(server):
    srv, launcher = server
    good = {"backend": "self-hosted", "preset": "qwen3-4b-instruct", "limit": "all", "shards": 20, "max_tokens": 6000}
    assert call(srv, "POST", "/api/runs", good)[0] == 403
    assert call(srv, "POST", "/api/runs", good, {"X-Launch-Key": "wrong"})[0] == 403
    status, reply = call(srv, "POST", "/api/runs", {**good, "preset": "nope"}, {"X-Launch-Key": "secret"})
    assert status == 400 and "preset" in reply["error"]
    status, reply = call(srv, "POST", "/api/runs", good, {"X-Launch-Key": "secret"})
    assert status == 202 and reply["workflow"] == "eval-local.yml"
    assert launcher.dispatched == [("eval-local.yml", {"preset": "qwen3-4b-instruct", "limit": "all", "shards": "20",
                                                       "max_tokens": "6000"})]
    paid = {"backend": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct", "allow_paid": True}
    status, reply = call(srv, "POST", "/api/runs", paid, {"X-Launch-Key": "secret"})
    assert status == 400 and "paid models are switched off" in reply["error"]
    assert len(launcher.dispatched) == 1


def test_server_without_a_token_cannot_launch(results):
    srv = ViewerServer(("127.0.0.1", 0), results_dir=results)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        assert call(srv, "GET", "/api/health")[1]["launch"] is False
        assert call(srv, "POST", "/api/runs", {"backend": "self-hosted"})[0] == 503
        assert call(srv, "GET", "/api/launches")[0] == 404
    finally:
        srv.shutdown()


@pytest.mark.parametrize(("body", "message"), [
    ({"backend": "cloud"}, "backend"),
    ({"backend": "self-hosted", "preset": "qwen3-4b-instruct", "shards": 21}, "shards"),
    ({"backend": "self-hosted", "preset": "qwen3-4b-instruct", "limit": "201"}, "limit"),
    ({"backend": "self-hosted", "preset": "qwen3-4b-instruct", "limit": "ten"}, "limit"),
    ({"backend": "openrouter", "model": "Bad Model; rm -rf"}, "model"),
    ({"backend": "openrouter", "model": "free", "reasoning_effort": "max"}, "reasoning_effort"),
])
def test_validate_rejects_bad_inputs(body, message):
    with pytest.raises(LaunchError, match=message):
        validate(body)


def test_validate_builds_workflow_inputs():
    assert validate({"backend": "openrouter", "model": "qwen/qwen3-8b:free", "limit": "10"}) == (
        "eval.yml", {"model": "qwen/qwen3-8b:free", "limit": "10", "allow_paid": "false", "max_tokens": "8000",
                     "reasoning_effort": ""})
    workflow, inputs = validate({"backend": "openrouter", "model": "x/y", "allow_paid": True}, allow_paid=True)
    assert inputs["allow_paid"] == "true"


def test_github_launcher_dispatches_and_lists_eval_runs():
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(204)
        return httpx.Response(200, json={"workflow_runs": [
            {"id": 1, "name": "Eval", "path": ".github/workflows/eval.yml", "status": "completed", "conclusion": "success",
             "created_at": "2026-10-26T00:00:00Z", "html_url": "u1"},
            {"id": 2, "name": "Tests", "path": ".github/workflows/tests.yml", "status": "completed"},
        ]})

    launcher = GitHubLauncher("me/ttune", "tok", client=httpx.Client(transport=httpx.MockTransport(handler)))
    launcher.dispatch("eval-local.yml", {"preset": "qwen3-4b-instruct"})
    post = seen[0]
    assert str(post.url) == "https://api.github.com/repos/me/ttune/actions/workflows/eval-local.yml/dispatches"
    assert post.headers["Authorization"] == "Bearer tok"
    assert json.loads(post.content) == {"ref": "main", "inputs": {"preset": "qwen3-4b-instruct"}}
    assert [r["id"] for r in launcher.recent()] == [1]

    refuse = GitHubLauncher("me/ttune", "tok", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(403, json={"message": "Resource not accessible"}))))
    with pytest.raises(LaunchError, match="HTTP 403"):
        refuse.dispatch("eval.yml", {})


def test_bad_request_bodies_are_refused(server):
    srv, launcher = server
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
    conn.putrequest("POST", "/api/runs")
    conn.putheader("X-Launch-Key", "secret")
    conn.putheader("Content-Length", "lots")
    conn.endheaders()
    assert conn.getresponse().status == 400
    conn.close()
    assert call(srv, "POST", "/api/runs", ["not", "an", "object"], {"X-Launch-Key": "secret"})[0] == 400
    assert launcher.dispatched == []
