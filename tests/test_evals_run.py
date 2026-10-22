"""`run` and `compare` end to end against a local mock of an OpenAI-compatible server. No network, no key."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from evals.__main__ import main
from evals.score import oracle_answer

SETS = Path(__file__).resolve().parents[1] / "data" / "households"
ROWS = {json.loads(line)["id"]: json.loads(line) for s in ("id", "ood") for line in (SETS / s / "households.jsonl").open()}
CASE_ID = re.compile(r"Case (\S+)")


def oracle_reply(case_id):
    row = ROWS[case_id]
    names = {m["name"]: m["id"] for m in row["household"]["members"]}
    return "Let me work through each program.\n```json\n" + json.dumps(oracle_answer(row["truth"], names)) + "\n```"


def deny_all_reply(case_id):
    return json.dumps({"snap": {"eligible": False, "monthly_benefit": 0}, "eitc": {"eligible": False, "annual_amount": 0},
                       "medicaid": {"eligible_members": []}, "wic": {"eligible_members": []}})


class Mock(BaseHTTPRequestHandler):
    seen: dict = {}
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def do_POST(self):
        assert self.path == "/v1/chat/completions"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["temperature"] == 0
        case_id = CASE_ID.search(body["messages"][1]["content"]).group(1)
        model = body["model"]
        with self.lock:
            Mock.seen[(model, case_id)] = Mock.seen.get((model, case_id), 0) + 1
            calls = Mock.seen[(model, case_id)]
        if model == "mock/fatal":
            return self._send(401, {"error": {"message": "bad key"}})
        if model == "mock/rate-limited":
            return self._send(429, {"error": {"message": "temporarily rate-limited upstream"}})
        if model == "mock/flaky" and calls == 1:
            return self._send(503, {"error": {"message": "busy"}})
        text = {"mock/oracle": oracle_reply, "mock/flaky": oracle_reply, "mock/deny-all": deny_all_reply,
                "mock/garbage": lambda _: "They probably qualify for something."}[model](case_id)
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": text}}],
                         "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0}})

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    httpd.shutdown()


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


def run_both(server, tmp_path, model, limit=6, extra=()):
    codes = [main(["run", "--set", s, "--model", model, "--limit", str(limit), "--run-id", "r", "--base-url", server,
                   "--results-dir", str(tmp_path), *extra]) for s in ("id", "ood")]
    return codes, tmp_path / "r"


def lines(path):
    return [json.loads(line) for line in path.open()]


def test_oracle_run_scores_one_and_compare_writes_every_section(server, tmp_path):
    codes, run_dir = run_both(server, tmp_path, "mock/oracle")
    assert codes == [0, 0]
    for s in ("id", "ood"):
        results = lines(run_dir / f"{s}.jsonl")
        assert [r["index"] for r in results] == list(range(6))
        assert all(r["status"] == "ok" and r["score"]["reward"] == 1.0 for r in results)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["model"] == "mock/oracle" and set(summary["sets"]) == {"id", "ood"}
    assert summary["sets"]["id"]["policyengine_us"] == "2.50.1"
    assert summary["sets"]["ood"]["prompt_tokens"] == 6000
    assert summary["sets"]["id"]["floors"]["always_no"] < 1
    assert main(["compare", "r", "--results-dir", str(tmp_path)]) == 0
    md = (run_dir / "comparison.md").read_text()
    for heading in ("## Overall", "## By program", "## OOD by shift family", "## OOD by twist"):
        assert heading in md
    assert "| Mean reward (0–1) | 1.00 | 1.00 | +0.00" in md
    assert "Threshold edge cases" in md and "Held-out states" in md and "Rare household shapes" in md


def test_deny_all_is_all_false_denials_and_balanced_accuracy_ignores_base_rates(server, tmp_path):
    # Mean reward for "always no" differs between the sets only because more OOD households qualify.
    # Balanced accuracy is 50% on both, so the comparison reports no ID -> OOD change for it.
    _, run_dir = run_both(server, tmp_path, "mock/deny-all", limit=200)
    from evals.metrics import summarize
    sid, sood = (summarize(lines(run_dir / f"{s}.jsonl")) for s in ("id", "ood"))
    for s in (sid, sood):
        assert s["malformed"] == 0
        assert all(s["programs"][p]["false_denial_rate"] == 1.0 for p in s["programs"])
        assert all(s["programs"][p]["balanced_accuracy"] == 0.5 for p in s["programs"])
    assert sid["reward"] != sood["reward"]
    main(["compare", "r", "--results-dir", str(tmp_path)])
    md = (run_dir / "comparison.md").read_text()
    assert md.count("| **Balanced accuracy** | 50% | 50% | +0 pts (+0 to +0) |") == 4


def test_garbage_replies_are_malformed_and_scored_zero(server, tmp_path):
    _, run_dir = run_both(server, tmp_path, "mock/garbage")
    results = lines(run_dir / "id.jsonl")
    assert all(r["score"]["malformed"] and r["score"]["reward"] == 0 and r["parse_error"] for r in results)
    assert json.loads((run_dir / "summary.json").read_text())["sets"]["id"]["malformed"] == 6


def test_server_errors_are_retried(server, tmp_path, monkeypatch):
    monkeypatch.setattr("evals.client.ChatClient._wait", lambda self, attempt, retry_after: _no_wait())
    codes, run_dir = run_both(server, tmp_path, "mock/flaky")
    assert codes == [0, 0]
    results = lines(run_dir / "id.jsonl")
    assert all(r["attempts"] == 2 and r["score"]["reward"] == 1.0 for r in results)


async def _no_wait():
    return None


def test_bad_key_stops_the_run(server, tmp_path):
    assert main(["run", "--set", "id", "--model", "mock/fatal", "--limit", "3", "--run-id", "r", "--base-url", server,
                 "--results-dir", str(tmp_path)]) == 2


def test_resume_only_runs_missing_cases(server, tmp_path):
    run_both(server, tmp_path, "mock/oracle", limit=3)
    before = dict(Mock.seen)
    codes, run_dir = run_both(server, tmp_path, "mock/oracle", limit=6, extra=("--resume",))
    assert codes == [0, 0]
    new_calls = {k: v - before.get(k, 0) for k, v in Mock.seen.items() if v != before.get(k, 0)}
    assert len(new_calls) == 6  # households 3-5 of each set
    assert len(lines(run_dir / "id.jsonl")) == 6 and not (run_dir / "id.partial.jsonl").exists()


def test_openrouter_needs_a_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from evals.client import ChatClient, FatalApiError
    with pytest.raises(FatalApiError, match="OPENROUTER_API_KEY"):
        ChatClient("some/model")


MODELS = [
    {"id": "meta-llama/llama-3.1-8b-instruct", "pricing": {"prompt": "0.00000002", "completion": "0.00000005"}},
    {"id": "qwen/qwen3-8b:free", "pricing": {"prompt": "0", "completion": "0", "request": "0"}},
    {"id": "odd/model", "pricing": {"prompt": "-1", "completion": "0"}},
]


def test_cost_guard_refuses_paid_models_unless_allowed():
    from evals.preflight import CostGuardError, choose_model
    with pytest.raises(CostGuardError, match="costs money"):
        choose_model(MODELS, "meta-llama/llama-3.1-8b-instruct", allow_paid=False)
    assert choose_model(MODELS, "meta-llama/llama-3.1-8b-instruct", allow_paid=True)["id"].endswith("instruct")
    with pytest.raises(CostGuardError, match="costs money"):
        choose_model(MODELS, "odd/model", allow_paid=False)  # anything not exactly $0 counts as paid
    with pytest.raises(CostGuardError, match="doesn't list"):
        choose_model(MODELS, "nope/nothing", allow_paid=True)


def test_free_picks_the_first_preferred_free_model():
    from evals.preflight import CostGuardError, choose_model
    assert choose_model(MODELS, "free", allow_paid=False)["id"] == "qwen/qwen3-8b:free"
    with pytest.raises(CostGuardError, match="free models now"):
        choose_model(MODELS[:1], "free", allow_paid=False)


def test_a_rate_limited_endpoint_stops_the_run_early(server, tmp_path, monkeypatch):
    monkeypatch.setattr("evals.client.ChatClient._wait", lambda self, attempt, retry_after: _no_wait())
    code = main(["run", "--set", "id", "--model", "mock/rate-limited", "--limit", "10", "--run-id", "r",
                 "--base-url", server, "--results-dir", str(tmp_path), "--concurrency", "1"])
    assert code == 2
    asked = {k for k in Mock.seen if k[0] == "mock/rate-limited"}
    assert len(asked) == 3  # gave up after three cases instead of trying all ten
