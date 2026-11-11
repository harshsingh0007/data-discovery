"""The only way the agent reaches the network.

Guardrails enforced here, not in prompts:
- https only, no IP literals, host must be on config/allowlist.json (redirects re-checked)
- byte cap per response (default from settings, hard cap cannot be exceeded)
- request budget per run
- read-only GET requests
Responses are cached on disk so reruns are cheap and reproducible. Use --no-cache to refresh.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ..config import ROOT
from ..trace import Trace


class HttpRefused(Exception):
    """A guardrail refused the request. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class HttpResult:
    url: str
    final_url: str
    status: int
    headers: dict
    body: bytes
    truncated: bool
    from_cache: bool
    elapsed_ms: int
    error: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or self.headers.get("Content-Type") or "").lower()

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def host_allowed(host: str, allowlist: list[str]) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in allowlist)


def _check_url(url: str, allowlist: list[str]) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise HttpRefused("SCHEME_NOT_ALLOWED", f"only https:// URLs are allowed, got {parts.scheme!r}")
    host = parts.hostname or ""
    try:
        ipaddress.ip_address(host)
        raise HttpRefused("IP_LITERAL_REFUSED", "IP-address URLs are refused; use a hostname on the allowlist")
    except ValueError:
        pass
    if not host_allowed(host, allowlist):
        raise HttpRefused("DOMAIN_NOT_ALLOWLISTED",
                          f"host {host!r} is not on config/allowlist.json. Do not try another route to it; "
                          "record the source as unreachable and say which host would need approval.")


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowlist: list[str]):
        self.allowlist = allowlist

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl, self.allowlist)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpClient:
    def __init__(self, settings: dict, allowlist: list[str], trace: Trace, use_cache: bool = True):
        cfg = settings["http"]
        self.timeout = cfg["timeout_s"]
        self.default_max = cfg["max_bytes_default"]
        self.hard_cap = cfg["max_bytes_hard_cap"]
        self.budget = cfg["max_requests_per_run"]
        self.user_agent = cfg["user_agent"]
        self.cache_dir = ROOT / cfg["cache_dir"]
        self.allowlist = allowlist
        self.trace = trace
        self.use_cache = use_cache
        self._count = 0
        self._lock = threading.Lock()
        self._opener = urllib.request.build_opener(_GuardedRedirects(allowlist))

    # -- cache -----------------------------------------------------------------
    def _cache_paths(self, url: str, max_bytes: int) -> tuple[Path, Path]:
        key = hashlib.sha256(f"{url}|{max_bytes}".encode()).hexdigest()[:32]
        return self.cache_dir / f"{key}.json", self.cache_dir / f"{key}.bin"

    def _from_cache(self, url: str, max_bytes: int) -> HttpResult | None:
        meta_p, body_p = self._cache_paths(url, max_bytes)
        if not (self.use_cache and meta_p.exists() and body_p.exists()):
            return None
        meta = json.loads(meta_p.read_text())
        return HttpResult(url=url, final_url=meta["final_url"], status=meta["status"], headers=meta["headers"],
                          body=body_p.read_bytes(), truncated=meta["truncated"], from_cache=True, elapsed_ms=0,
                          meta={"cached_at": meta.get("cached_at")})

    def _to_cache(self, res: HttpResult, max_bytes: int) -> None:
        if res.status != 200 or res.error:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        meta_p, body_p = self._cache_paths(res.url, max_bytes)
        tmp = body_p.with_suffix(".tmp")
        tmp.write_bytes(res.body)
        tmp.replace(body_p)
        meta_p.write_text(json.dumps({"final_url": res.final_url, "status": res.status, "headers": res.headers,
                                      "truncated": res.truncated, "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))

    # -- request ---------------------------------------------------------------
    def get(self, url: str, max_bytes: int | None = None, agent: str = "") -> HttpResult:
        max_bytes = min(int(max_bytes or self.default_max), self.hard_cap)
        try:
            _check_url(url, self.allowlist)
        except HttpRefused as exc:
            self.trace.event("http", agent=agent, url=url, refused=exc.code)
            raise
        cached = self._from_cache(url, max_bytes)
        if cached is not None:
            self.trace.event("http", agent=agent, url=url, status=cached.status, bytes=len(cached.body), from_cache=True)
            return cached
        with self._lock:
            if self._count >= self.budget:
                self.trace.event("http", agent=agent, url=url, refused="REQUEST_BUDGET_EXHAUSTED")
                raise HttpRefused("REQUEST_BUDGET_EXHAUSTED", f"run budget of {self.budget} HTTP requests used up")
            self._count += 1

        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "*/*"}, method="GET")
        started = time.time()
        status, headers, body, truncated, final_url, error = 0, {}, b"", False, url, None
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                status = resp.status
                headers = {k.lower(): v for k, v in resp.headers.items()}
                final_url = resp.geturl()
                body = resp.read(max_bytes + 1)
                if len(body) > max_bytes:
                    body, truncated = body[:max_bytes], True
        except HttpRefused:
            self.trace.event("http", agent=agent, url=url, refused="REDIRECT_NOT_ALLOWLISTED")
            raise
        except urllib.error.HTTPError as exc:
            status, headers = exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}
            error = f"HTTP {exc.code} {exc.reason}"
            try:
                body = exc.read(20000)
            except Exception:  # noqa: BLE001 - best effort body read on error
                body = b""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"
        res = HttpResult(url=url, final_url=final_url, status=status, headers=headers, body=body, truncated=truncated,
                         from_cache=False, elapsed_ms=int((time.time() - started) * 1000), error=error)
        self.trace.event("http", agent=agent, url=url, status=status, bytes=len(body), truncated=truncated,
                         error=error, elapsed_ms=res.elapsed_ms)
        self._to_cache(res, max_bytes)
        return res

    def get_json(self, url: str, max_bytes: int | None = None, agent: str = ""):
        res = self.get(url, max_bytes=max_bytes, agent=agent)
        if res.error:
            raise RuntimeError(f"{res.error} for {url}")
        if res.truncated:
            raise RuntimeError(f"response for {url} exceeded {max_bytes or self.default_max} bytes; "
                               "refusing to parse a truncated JSON document")
        return json.loads(res.body.decode("utf-8", errors="replace")), res
