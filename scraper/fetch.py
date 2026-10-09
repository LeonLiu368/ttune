from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "ttune-scraper/0.1 (+https://github.com/LeonLiu368/ttune)"
MAX_BYTES = 50 * 1024 * 1024
RETRY_STATUSES = {429, 500, 502, 503, 504}
META_FILE = "_fetch.json"

EXTENSIONS = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
}


class FetchError(Exception):
    pass


@dataclass
class Fetched:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes


class Http:
    def __init__(self, client: httpx.Client, min_interval: float = 1.0, retries: int = 3, backoff: float = 2.0):
        self.client = client
        self.min_interval = min_interval
        self.retries = retries
        self.backoff = backoff
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, tuple[RobotFileParser | None, str]] = {}

    def get(self, url: str) -> Fetched:
        reason = self._robots_check(url)
        if reason:
            raise FetchError(f"disallowed by robots.txt ({reason}): {url}")
        return self._get(url)

    def _robots_check(self, url: str) -> str | None:
        """Return why robots.txt disallows the URL, or None if it's allowed."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            reason = "its rules disallow this path"
            try:
                resp = self._get(origin + "/robots.txt")
            except FetchError:
                # Unreachable robots.txt: the real request will surface the network problem.
                parser = None
            else:
                if resp.status in (401, 403):
                    parser.disallow_all = True
                    reason = f"robots.txt itself returned HTTP {resp.status}"
                elif resp.status == 200:
                    parser.parse(resp.body.decode("utf-8", "replace").splitlines())
                else:
                    parser.allow_all = True
            self._robots[origin] = (parser, reason)
        parser, reason = self._robots[origin]
        if parser is None or parser.can_fetch(USER_AGENT, url):
            return None
        return reason

    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            delay = self.min_interval - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
        self._last_request[host] = time.monotonic()

    def _get(self, url: str) -> Fetched:
        host = urlsplit(url).netloc
        error = ""
        for attempt in range(self.retries):
            if attempt:
                time.sleep(self.backoff * 2 ** (attempt - 1))
            self._throttle(host)
            try:
                with self.client.stream(
                    "GET", url, headers={"User-Agent": USER_AGENT}, follow_redirects=True
                ) as resp:
                    if resp.status_code in RETRY_STATUSES:
                        error = f"HTTP {resp.status_code}"
                        continue
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise FetchError(f"larger than {MAX_BYTES} bytes: {url}")
                    return Fetched(
                        url=url,
                        final_url=str(resp.url),
                        status=resp.status_code,
                        content_type=resp.headers.get("content-type", ""),
                        body=bytes(body),
                    )
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"
        raise FetchError(f"{error} after {self.retries} attempts: {url}")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def extract_links(page: Fetched, pattern: str, hosts: list[str] | None, limit: int) -> list[str]:
    parser = _LinkParser()
    parser.feed(page.body.decode("utf-8", "replace"))
    allowed_hosts = set(hosts) if hosts else {urlsplit(page.final_url).hostname}
    regex = re.compile(pattern)
    links: list[str] = []
    for href in parser.hrefs:
        url = urljoin(page.final_url, href).split("#", 1)[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.hostname not in allowed_hosts:
            continue
        if regex.search(url) and url not in links:
            links.append(url)
        if len(links) >= limit:
            break
    return links


def first_ok(http: Http, urls: list[str]) -> Fetched:
    errors = []
    for url in urls:
        try:
            resp = http.get(url)
        except FetchError as exc:
            errors.append(str(exc))
            continue
        if resp.status == 200:
            return resp
        errors.append(f"HTTP {resp.status}: {url}")
    raise FetchError("; ".join(errors))


def collect(http: Http, config: dict) -> tuple[list[Fetched], list[str]]:
    """Fetch everything one source's config describes. Returns (files, errors for linked files)."""
    main = first_ok(http, config["urls"])
    files, errors = [main], []
    follow = config.get("follow")
    if config["type"] == "page" and follow:
        for link in extract_links(main, follow["pattern"], follow.get("hosts"), follow.get("max", 10)):
            try:
                files.append(first_ok(http, [link]))
            except FetchError as exc:
                errors.append(str(exc))
    elif config["type"] not in ("direct", "page"):
        raise FetchError(f"unknown fetch type {config['type']!r}")
    return files, errors


def filename_for(fetched: Fetched) -> str:
    name = unquote(Path(urlsplit(fetched.final_url).path).name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).lstrip("._-")[:120]
    mime = fetched.content_type.split(";", 1)[0].strip().lower()
    if not Path(name).suffix:
        name = (name or "page") + EXTENSIONS.get(mime, ".bin")
    return name


def _unique(name: str, taken: set[str]) -> str:
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{stem}-{n}{suffix}", n + 1
    taken.add(candidate)
    return candidate


def latest_snapshot(source_dir: Path) -> Path | None:
    snapshots = sorted(p for p in source_dir.glob("*") if (p / META_FILE).is_file())
    return snapshots[-1] if snapshots else None


def _signature(entries: list[dict]) -> list[tuple[str, str]]:
    return sorted((e["url"], e["sha256"]) for e in entries)


def save_snapshot(source_dir: Path, files: list[Fetched], errors: list[str], now: datetime) -> Path | None:
    """Write a new snapshot, or return None if content matches the latest one."""
    taken: set[str] = set()
    entries = [
        {
            "file": _unique(filename_for(f), taken),
            "url": f.url,
            "final_url": f.final_url,
            "status": f.status,
            "content_type": f.content_type,
            "bytes": len(f.body),
            "sha256": hashlib.sha256(f.body).hexdigest(),
        }
        for f in files
    ]
    latest = latest_snapshot(source_dir)
    if latest and _signature(json.loads((latest / META_FILE).read_text())["files"]) == _signature(entries):
        return None

    snapshot = source_dir / now.strftime("%Y-%m-%d")
    if snapshot.exists():
        snapshot = source_dir / now.strftime("%Y-%m-%dT%H%M%SZ")
    snapshot.mkdir(parents=True)
    for f, entry in zip(files, entries):
        (snapshot / entry["file"]).write_bytes(f.body)
    meta = {"fetched_at": now.isoformat(timespec="seconds"), "files": entries, "errors": errors}
    (snapshot / META_FILE).write_text(json.dumps(meta, indent=2) + "\n")
    return snapshot


def fetch_source(http: Http, source: dict, data_dir: Path, now: datetime | None = None) -> dict:
    """Fetch one source, update its sources.json entry in place, and return a result row."""
    now = now or datetime.now(timezone.utc)
    source_id = source["id"]
    source_dir = data_dir / "raw" / source_id
    try:
        files, errors = collect(http, source["fetch"])
    except FetchError as exc:
        source["status"] = "error"
        source["last_error"] = str(exc)
        return {"id": source_id, "result": "error", "files": 0, "notes": str(exc)}

    snapshot = save_snapshot(source_dir, files, errors, now)
    source["status"] = "partial" if errors else "fetched"
    source["local_path"] = f"raw/{source_id}"
    if errors:
        source["last_error"] = "; ".join(errors)
    else:
        source.pop("last_error", None)
    if snapshot is None:
        result = "unchanged"
    else:
        result = "partial" if errors else "new"
        source["retrieved"] = now.date().isoformat()
        source["latest_snapshot"] = snapshot.relative_to(data_dir).as_posix()
    return {"id": source_id, "result": result, "files": len(files), "notes": "; ".join(errors)}
