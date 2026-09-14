"""Retry, backoff and rate-limit behaviour, with the socket call stubbed out."""
import asyncio
import dataclasses
import json
import time
import unittest
import urllib.error

from server.config import Config
from server.errors import SourceError, SourceRateLimited, SourceUnavailable
from server.sources.http import Fetcher, RateLimiter, _backoff, _explain, _redact, \
    _Retryable, default_user_agent


def cfg(**kw):
    return dataclasses.replace(Config(), max_backoff=0.01, max_attempts=3, **kw)


class Scripted(Fetcher):
    """A Fetcher whose one network call is a list of scripted outcomes."""

    def __init__(self, config, outcomes):
        super().__init__(config)
        self.outcomes = list(outcomes)
        self.calls = 0

    def _get(self, url, headers):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestRetries(unittest.TestCase):
    def test_transient_failure_then_success(self):
        f = Scripted(cfg(), [_Retryable("HTTP 503", status=503), {"ok": True}])
        self.assertEqual(asyncio.run(f.get_json("https://x/works")), {"ok": True})
        self.assertEqual(f.calls, 2)

    def test_gives_up_after_max_attempts(self):
        f = Scripted(cfg(), [_Retryable("HTTP 503", status=503)] * 3)
        with self.assertRaises(SourceUnavailable):
            asyncio.run(f.get_json("https://x/works"))
        self.assertEqual(f.calls, 3)

    def test_repeated_429_surfaces_as_rate_limited(self):
        f = Scripted(cfg(), [_Retryable("slow down", retry_after=0.001, status=429)] * 3)
        with self.assertRaises(SourceRateLimited):
            asyncio.run(f.get_json("https://x/works"))

    def test_a_long_retry_after_fails_immediately(self):
        # OpenAlex answers an exhausted budget with a wait measured in hours.
        f = Scripted(cfg(), [_Retryable("Insufficient budget", retry_after=27072, status=429)])
        with self.assertRaises(SourceRateLimited) as ctx:
            asyncio.run(f.get_json("https://api.openalex.org/works", source="OpenAlex"))
        self.assertEqual(ctx.exception.retry_after, 27072)
        self.assertEqual(f.calls, 1)
        self.assertIn("budget", ctx.exception.message)

    def test_non_retryable_status_is_not_retried(self):
        err = urllib.error.HTTPError("https://x", 404, "Not Found", {}, None)
        f = Scripted(cfg(), [err])
        with self.assertRaises(SourceError) as ctx:
            asyncio.run(f.get_json("https://x/works"))
        self.assertEqual(ctx.exception.detail["status"], 404)
        self.assertEqual(f.calls, 1)

    def test_socket_errors_are_retried(self):
        f = Scripted(cfg(), [TimeoutError("timed out"), {"ok": 1}])
        self.assertEqual(asyncio.run(f.get_json("https://x/works")), {"ok": 1})

    def test_params_are_sent_and_nulls_dropped(self):
        seen = {}

        class Recorder(Scripted):
            def _get(self, url, headers):
                seen["url"] = url
                return super()._get(url, headers)

        f = Recorder(cfg(), [{"ok": 1}])
        asyncio.run(f.get_json("https://x/works", {"search": "a b", "api_key": None}))
        self.assertIn("search=a+b", seen["url"])
        self.assertNotIn("api_key", seen["url"])


class TestErrorReading(unittest.TestCase):
    def test_retry_after_header(self):
        err = urllib.error.HTTPError("https://x", 429, "Too Many", {"Retry-After": "12"}, None)
        err.read = lambda *a: b""
        message, retry_after, status = _explain(err)
        self.assertEqual((retry_after, status), (12.0, 429))

    def test_openalex_body_carries_the_wait(self):
        body = json.dumps({"message": "Insufficient budget", "retryAfter": 27072}).encode()
        err = urllib.error.HTTPError("https://x", 429, "Too Many", {}, None)
        err.read = lambda *a: body
        message, retry_after, _ = _explain(err)
        self.assertEqual(message, "Insufficient budget")
        self.assertEqual(retry_after, 27072.0)

    def test_unreadable_body_still_explains_the_status(self):
        err = urllib.error.HTTPError("https://x", 502, "Bad Gateway", {}, None)
        err.read = lambda *a: b"<html>"
        self.assertEqual(_explain(err)[0], "HTTP 502")


class TestPolitenessAndSafety(unittest.TestCase):
    def test_rate_limiter_spaces_requests_out(self):
        async def go():
            limiter = RateLimiter(rate=40, burst=1)
            start = time.monotonic()
            for _ in range(3):
                await limiter.acquire()
            return time.monotonic() - start

        self.assertGreater(asyncio.run(go()), 0.03)

    def test_backoff_grows_and_is_capped(self):
        # 0.5s base for the first retry, +/- the jitter band.
        self.assertTrue(0.37 <= _backoff(1, 10) <= 0.63)
        self.assertTrue(0.75 <= _backoff(2, 10) <= 1.25)
        self.assertLessEqual(_backoff(9, 2), 2.5)

    def test_api_keys_are_redacted(self):
        self.assertIn("api_key=redacted", _redact("https://x/works?api_key=secret&search=a"))
        self.assertNotIn("secret", _redact("https://x/works?api_key=secret&search=a"))
        self.assertEqual(_redact("https://x/works"), "https://x/works")

    def test_user_agent_identifies_us_and_uses_contact_when_given(self):
        self.assertNotIn("mailto", default_user_agent(Config()))
        self.assertIn("mailto:a@b.org", default_user_agent(cfg(contact="a@b.org")))


if __name__ == "__main__":
    unittest.main()
