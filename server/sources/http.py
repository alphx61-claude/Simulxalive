"""HTTP for adapters: one polite, rate-limited, retrying JSON GET.

urllib in a worker thread keeps the dependency list empty. The rules that matter
are here rather than in each adapter: identify ourselves, stay under the rate,
honour Retry-After, and refuse to sit on a socket for hours when an upstream
says its budget is gone.
"""
import asyncio
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request

from ..errors import SourceError, SourceRateLimited, SourceUnavailable

log = logging.getLogger("simulxalive.http")

RETRY_STATUS = {429, 500, 502, 503, 504}


class RateLimiter:
    """Token bucket, shared by every request to one upstream."""

    def __init__(self, rate, burst):
        self.rate = max(rate, 0.1)
        self.burst = max(burst, 1)
        self._tokens = float(self.burst)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.burst, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)


class Fetcher:
    """Shared HTTP client. One per server process."""

    def __init__(self, cfg, *, user_agent=None):
        self.cfg = cfg
        self.user_agent = user_agent or default_user_agent(cfg)
        self._limiter = RateLimiter(cfg.rate_per_second, cfg.rate_burst)

    async def get_json(self, url, params=None, *, headers=None, source="upstream"):
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            url = f"{url}?{urllib.parse.urlencode(clean)}"
        last = None
        for attempt in range(1, self.cfg.max_attempts + 1):
            await self._limiter.acquire()
            try:
                return await asyncio.to_thread(self._get, url, headers or {})
            except _Retryable as e:
                last = e
                wait = e.retry_after if e.retry_after is not None else _backoff(
                    attempt, self.cfg.max_backoff)
                if e.retry_after is not None and e.retry_after > self.cfg.max_retry_wait:
                    raise SourceRateLimited(
                        f"{source} asked for a {int(e.retry_after)}s wait: {e.message}",
                        retry_after=e.retry_after, detail={"url": _redact(url)})
                if attempt == self.cfg.max_attempts:
                    break
                log.info("%s %s, retrying in %.1fs (%d/%d)",
                         source, e.message, wait, attempt, self.cfg.max_attempts)
                await asyncio.sleep(wait)
            except urllib.error.HTTPError as e:
                raise SourceError(f"{source} returned {e.code}: {e.reason}",
                                  detail={"status": e.code, "url": _redact(url)})
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = _Retryable(str(e))
                if attempt == self.cfg.max_attempts:
                    break
                await asyncio.sleep(_backoff(attempt, self.cfg.max_backoff))

        message = last.message if last else "unknown failure"
        if last is not None and last.status == 429:
            raise SourceRateLimited(f"{source} is rate limiting us: {message}",
                                    retry_after=last.retry_after)
        raise SourceUnavailable(f"{source} unreachable after {self.cfg.max_attempts} attempts: "
                                f"{message}", detail={"url": _redact(url)})

    def _get(self, url, headers):
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent,
                                                   "Accept": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout) as resp:
                body = resp.read(self.cfg.max_response_bytes + 1)
                if len(body) > self.cfg.max_response_bytes:
                    raise SourceError(f"response over {self.cfg.max_response_bytes} bytes")
                try:
                    return json.loads(body)
                except json.JSONDecodeError as e:
                    raise SourceError(f"upstream sent something that is not json: {e}")
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS:
                raise _Retryable(*_explain(e))
            raise


class _Retryable(Exception):
    def __init__(self, message, retry_after=None, status=None):
        super().__init__(message)
        self.message, self.retry_after, self.status = message, retry_after, status


def _explain(e):
    """Pull the wait and the reason out of an error response."""
    retry_after, message = None, f"HTTP {e.code}"
    header = e.headers.get("Retry-After") if e.headers else None
    if header:
        try:
            retry_after = float(header)
        except ValueError:
            retry_after = None
    try:
        body = json.loads(e.read(64 * 1024))
        message = body.get("message") or body.get("error") or message
        # OpenAlex reports its own wait in the body when a budget runs out.
        if retry_after is None and isinstance(body.get("retryAfter"), (int, float)):
            retry_after = float(body["retryAfter"])
    except Exception:
        pass
    return message, retry_after, e.code


def _backoff(attempt, ceiling):
    return min(ceiling, (2 ** (attempt - 1)) * 0.5) * (0.75 + random.random() * 0.5)


def _redact(url):
    """Keep api keys out of anything a client or a log file sees."""
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    q = [(k, "redacted" if k in ("api_key", "token", "key") else v)
         for k, v in urllib.parse.parse_qsl(parts.query)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))


def default_user_agent(cfg):
    ua = "simulxalive-ingest/0.1 (+https://github.com/alphx61-claude/simulxalive)"
    return f"{ua} mailto:{cfg.contact}" if cfg.contact else ua
