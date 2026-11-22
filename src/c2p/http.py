"""Cached, rate-limited HTTP GET for scholarly APIs (Crossref, Semantic Scholar, OpenAlex, arXiv).

Every response (including 404s) is cached on disk keyed by the URL with
credentials and `mailto` removed, so a rerun makes no network calls and recorded
responses can be shipped as test fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .common import C2PError

USER_AGENT = "code2paper/0.1 (citation audit; https://github.com/)"
MIN_INTERVAL = {
    "api.crossref.org": 0.25,
    "api.semanticscholar.org": 1.1,
    "api.openalex.org": 0.2,
    "export.arxiv.org": 3.0,
}


@dataclass
class Response:
    status: int
    body: str

    def json(self) -> object:
        return json.loads(self.body) if self.body else None


@dataclass
class CachedClient:
    cache_dir: Path
    offline: bool = False
    mailto: str | None = None
    s2_key: str | None = field(default_factory=lambda: os.environ.get("SEMANTIC_SCHOLAR_API_KEY"))
    network_calls: int = 0
    failures: list[tuple[str, int]] = field(default_factory=list)
    max_retries: int = 5
    _last: dict[str, float] = field(default_factory=dict)

    def _key(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k not in {"mailto", "api_key"}]
        norm = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(sorted(q))))
        return hashlib.sha256(norm.encode()).hexdigest()[:32]

    def _cache_path(self, url: str) -> Path:
        host = urllib.parse.urlsplit(url).netloc.replace(":", "_")
        return self.cache_dir / host / f"{self._key(url)}.json"

    def get(self, url: str) -> Response:
        cp = self._cache_path(url)
        if cp.exists():
            d = json.loads(cp.read_text(encoding="utf-8"))
            return Response(d["status"], d["body"])
        if self.offline:
            self.failures.append((self._strip_secrets(url), 0))
            return Response(0, "")
        resp = self._fetch(url)
        if resp.status not in (200, 404, 400):
            self.failures.append((self._strip_secrets(url), resp.status))
        if resp.status in (200, 404, 400):
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(
                json.dumps({"url": self._strip_secrets(url), "status": resp.status, "body": resp.body}),
                encoding="utf-8",
            )
        return resp

    def _strip_secrets(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k not in {"mailto", "api_key"}]
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))

    def _throttle(self, host: str) -> None:
        gap = MIN_INTERVAL.get(host, 0.5)
        if host == "api.semanticscholar.org" and self.s2_key:
            gap = 0.35
        wait = self._last.get(host, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _fetch(self, url: str) -> Response:
        host = urllib.parse.urlsplit(url).netloc
        if host == "api.crossref.org" and self.mailto:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}mailto={urllib.parse.quote(self.mailto)}"
        headers = {"User-Agent": USER_AGENT}
        if host == "api.semanticscholar.org" and self.s2_key:
            headers["x-api-key"] = self.s2_key
        delay = 2.0
        for attempt in range(self.max_retries):
            self._throttle(host)
            self.network_calls += 1
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return Response(r.status, r.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries - 1:
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
                    delay *= 2
                    continue
                return Response(e.code, e.read().decode("utf-8", errors="replace") if e.fp else "")
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise C2PError(f"network error for {url}: {e}") from e
        raise C2PError(f"giving up on {url}")
