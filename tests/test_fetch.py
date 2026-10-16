import http.server
import json
import threading
from datetime import datetime, timezone

import httpx
import pytest

from scraper import fetch as fetch_mod
from scraper.__main__ import main
from scraper.fetch import Fetched, Http, fetch_source, filename_for, import_files

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 9, 13, 30, 0, tzinfo=timezone.utc)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.hits.append(self.path)
        responses = self.server.routes.get(self.path)
        if responses is None:
            self.send_response(404)
            self.end_headers()
            return
        if isinstance(responses, list):
            response = responses.pop(0) if len(responses) > 1 else responses[0]
        else:
            response = responses
        status, headers, body = response
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.routes, srv.hits = {}, []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.base = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def client():
    # trust_env=False so a proxy configured in the environment never sees localhost traffic.
    with httpx.Client(trust_env=False, timeout=5) as c:
        yield Http(c, min_interval=0, retries=2, backoff=0)


def ok(body: bytes, ctype: str = "application/pdf"):
    return (200, {"Content-Type": ctype}, body)


def direct(source_id: str, *urls: str) -> dict:
    return {"id": source_id, "status": "todo", "fetch": {"type": "direct", "urls": list(urls)}}


def test_direct_fetch_writes_snapshot_and_updates_source(server, client, tmp_path):
    server.routes["/doc.pdf"] = ok(b"%PDF-1 hello")
    source = direct("irs", f"{server.base}/doc.pdf")

    row = fetch_source(client, source, tmp_path, NOW)

    snapshot = tmp_path / "raw" / "irs" / "2026-10-09"
    assert (snapshot / "doc.pdf").read_bytes() == b"%PDF-1 hello"
    meta = json.loads((snapshot / "_fetch.json").read_text())
    assert meta["files"][0]["sha256"] == fetch_mod.hashlib.sha256(b"%PDF-1 hello").hexdigest()
    assert row["result"] == "new"
    assert source["status"] == "fetched"
    assert source["retrieved"] == "2026-10-09"
    assert source["latest_snapshot"] == "raw/irs/2026-10-09"


def test_unchanged_content_does_not_create_snapshot(server, client, tmp_path):
    server.routes["/doc.pdf"] = ok(b"same")
    source = direct("irs", f"{server.base}/doc.pdf")
    fetch_source(client, source, tmp_path, NOW)
    before = json.dumps(source, sort_keys=True)

    row = fetch_source(client, source, tmp_path, LATER)

    assert row["result"] == "unchanged"
    assert [p.name for p in (tmp_path / "raw" / "irs").iterdir()] == ["2026-10-09"]
    # Nothing in sources.json changes, so the scheduled workflow opens no PR.
    assert json.dumps(source, sort_keys=True) == before


def test_changed_content_same_day_gets_timestamped_snapshot(server, client, tmp_path):
    server.routes["/doc.pdf"] = [ok(b"v1"), ok(b"v2")]
    source = direct("irs", f"{server.base}/doc.pdf")
    fetch_source(client, source, tmp_path, NOW)

    row = fetch_source(client, source, tmp_path, LATER)

    assert row["result"] == "new"
    assert source["latest_snapshot"] == "raw/irs/2026-10-09T133000Z"
    assert (tmp_path / "raw/irs/2026-10-09T133000Z/doc.pdf").read_bytes() == b"v2"


def test_falls_back_to_next_url(server, client, tmp_path):
    server.routes["/good.xlsx"] = ok(b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    source = direct("sua", f"{server.base}/missing.xlsx", f"{server.base}/good.xlsx")

    fetch_source(client, source, tmp_path, NOW)

    meta = json.loads((tmp_path / "raw/sua/2026-10-09/_fetch.json").read_text())
    assert meta["files"][0]["url"].endswith("/good.xlsx")


def test_all_urls_failing_records_error_without_snapshot(server, client, tmp_path):
    source = direct("gone", f"{server.base}/a.pdf", f"{server.base}/b.pdf")

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "error"
    assert source["status"] == "error"
    assert "HTTP 404" in source["last_error"]
    assert not (tmp_path / "raw" / "gone").exists()


def test_retries_transient_errors(server, client, tmp_path):
    server.routes["/flaky.csv"] = [(503, {}, b""), ok(b"a,b\n1,2\n", "text/csv")]
    source = direct("medicaid", f"{server.base}/flaky.csv")

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "new"
    assert server.hits.count("/flaky.csv") == 2


def test_records_final_url_after_redirect(server, client, tmp_path):
    server.routes["/old"] = (302, {"Location": "/new/form.pdf"}, b"")
    server.routes["/new/form.pdf"] = ok(b"pdf")
    source = direct("w2", f"{server.base}/old")

    fetch_source(client, source, tmp_path, NOW)

    meta = json.loads((tmp_path / "raw/w2/2026-10-09/_fetch.json").read_text())
    assert meta["files"][0]["final_url"] == f"{server.base}/new/form.pdf"
    assert meta["files"][0]["file"] == "form.pdf"


def test_page_follows_matching_links_on_allowed_hosts(server, client, tmp_path):
    other_host = f"http://localhost:{server.server_port}"
    page = f"""
      <a href="memo.pdf">memo</a>
      <a href="/files/tables.pdf#page=2">tables</a>
      <a href="memo.pdf">duplicate</a>
      <a href="notes.txt">not a pdf</a>
      <a href="{other_host}/elsewhere.pdf">other host</a>
      <a href="mailto:x@example.com">mail</a>
    """.encode()
    server.routes["/cola/fy27"] = ok(page, "text/html; charset=utf-8")
    server.routes["/cola/memo.pdf"] = ok(b"memo")
    server.routes["/files/tables.pdf"] = ok(b"tables")
    source = {
        "id": "cola",
        "fetch": {"type": "page", "urls": [f"{server.base}/cola/fy27"], "follow": {"pattern": r"\.pdf$"}},
    }

    row = fetch_source(client, source, tmp_path, NOW)

    files = sorted(p.name for p in (tmp_path / "raw/cola/2026-10-09").iterdir())
    assert files == ["_fetch.json", "fy27.html", "memo.pdf", "tables.pdf"]
    assert "/elsewhere.pdf" not in server.hits
    assert row["files"] == 3


def test_page_follow_respects_host_allowlist_and_limit(server, client, tmp_path):
    other_host = f"http://localhost:{server.server_port}"
    page = f'<a href="a.pdf">a</a><a href="{other_host}/b.pdf">b</a><a href="c.pdf">c</a>'.encode()
    server.routes["/p"] = ok(page, "text/html")
    server.routes["/a.pdf"] = ok(b"a")
    server.routes["/b.pdf"] = ok(b"b")
    source = {
        "id": "p",
        "fetch": {
            "type": "page",
            "urls": [f"{server.base}/p"],
            "follow": {"pattern": r"\.pdf$", "hosts": ["127.0.0.1", "localhost"], "max": 2},
        },
    }

    fetch_source(client, source, tmp_path, NOW)

    assert server.hits.count("/b.pdf") == 1
    assert "/c.pdf" not in server.hits


def test_failed_linked_file_marks_source_partial(server, client, tmp_path):
    server.routes["/p"] = ok(b'<a href="ok.pdf"></a><a href="broken.pdf"></a>', "text/html")
    server.routes["/ok.pdf"] = ok(b"ok")
    source = {"id": "p", "fetch": {"type": "page", "urls": [f"{server.base}/p"], "follow": {"pattern": r"\.pdf$"}}}

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "partial"
    assert source["status"] == "partial"
    assert "broken.pdf" in source["last_error"]
    meta = json.loads((tmp_path / "raw/p/2026-10-09/_fetch.json").read_text())
    assert len(meta["files"]) == 2 and meta["errors"]


def test_robots_disallow_skips_fetch(server, client, tmp_path):
    server.routes["/robots.txt"] = ok(b"User-agent: *\nDisallow: /private/\n", "text/plain")
    server.routes["/private/doc.pdf"] = ok(b"secret")
    source = direct("blocked", f"{server.base}/private/doc.pdf")

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "error"
    assert "its rules disallow this path" in source["last_error"]
    assert "/private/doc.pdf" not in server.hits


def test_robots_txt_client_error_means_no_restrictions(server, client, tmp_path):
    server.routes["/robots.txt"] = (403, {}, b"")
    server.routes["/doc.pdf"] = ok(b"pdf")
    source = direct("open", f"{server.base}/doc.pdf")

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "new"


def test_robots_txt_server_error_disallows_everything(server, client, tmp_path):
    server.routes["/robots.txt"] = (503, {}, b"")
    server.routes["/doc.pdf"] = ok(b"pdf")
    source = direct("down", f"{server.base}/doc.pdf")

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "error"
    assert "robots.txt unreachable" in source["last_error"]
    assert "/doc.pdf" not in server.hits


def test_oversized_download_is_rejected(server, client, tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod, "MAX_BYTES", 10)
    server.routes["/big.pdf"] = ok(b"x" * 100)
    source = direct("big", f"{server.base}/big.pdf")

    row = fetch_source(client, source, tmp_path, NOW)

    assert row["result"] == "error"
    assert "larger than" in source["last_error"]


@pytest.mark.parametrize(
    ("url", "ctype", "expected"),
    [
        ("https://x.gov/a/..%2F..%2Fetc%2Fpasswd", "text/plain", "etc_passwd.bin"),
        ("https://x.gov/snap/cola/fy27", "text/html; charset=utf-8", "fy27.html"),
        ("https://x.gov/", "text/html", "page.html"),
        ("https://x.gov/files/FY%202021%20Tech%20Doc.pdf", "application/pdf", "FY_2021_Tech_Doc.pdf"),
        ("https://x.gov/.hidden.csv", "text/csv", "hidden.csv"),
    ],
)
def test_filename_is_safe_and_has_extension(url, ctype, expected):
    assert filename_for(Fetched(url, url, 200, ctype, b"")) == expected


def test_cli_rejects_unknown_source(tmp_path, capsys):
    (tmp_path / "sources.json").write_text(json.dumps({"sources": [direct("known", "https://x.gov/a.pdf")]}))

    assert main(["--data-dir", str(tmp_path), "fetch", "--source", "nope"]) == 2
    assert "nope" in capsys.readouterr().err


def test_import_snapshots_hand_downloaded_files(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "FY27 COLA memo.pdf").write_bytes(b"%PDF memo")
    source = {"id": "cola", "url": "https://www.usda.gov/cola", "status": "todo"}

    row = import_files(source, [downloads / "FY27 COLA memo.pdf"], "https://www.usda.gov/memo.pdf", tmp_path, NOW)

    snapshot = tmp_path / "raw/cola/2026-10-09"
    assert (snapshot / "FY27_COLA_memo.pdf").read_bytes() == b"%PDF memo"
    meta = json.loads((snapshot / "_fetch.json").read_text())
    assert meta["method"] == "manual"
    assert meta["files"][0]["url"] == "https://www.usda.gov/memo.pdf"
    assert meta["files"][0]["content_type"] == "application/pdf"
    assert row["result"] == "new" and source["status"] == "fetched"


def _sources_file(tmp_path, *sources):
    (tmp_path / "sources.json").write_text(json.dumps({"sources": list(sources)}))


def _where(source_id, where):
    return {"id": source_id, "url": "https://x.gov", "fetch": {"type": "direct", "urls": ["http://127.0.0.1:9/x"], "where": where}}


def test_ci_skips_local_and_manual_sources(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr("scraper.__main__.fetch_source", lambda http, s, d: called.append(s["id"]) or
                        {"id": s["id"], "result": "new", "files": 1, "notes": ""})
    _sources_file(tmp_path, _where("a", "anywhere"), _where("l", "local"), _where("m", "manual"))
    summary = tmp_path / "summary.md"

    assert main(["--data-dir", str(tmp_path), "fetch", "--ci", "--summary", str(summary)]) == 0
    assert called == ["a"]
    assert "| `l` | skipped |" in summary.read_text() and "| `m` | skipped |" in summary.read_text()

    called.clear()
    main(["--data-dir", str(tmp_path), "fetch"])
    assert called == ["a", "l"]

    called.clear()
    main(["--data-dir", str(tmp_path), "fetch", "--source", "m"])
    assert called == ["m"]
