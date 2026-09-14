"""End to end over a real socket, with a fake source in place of the network."""
import asyncio
import dataclasses
import json
import pathlib
import tempfile
import unittest

from server import sources
from server.config import Config
from server.errors import SourceRateLimited
from server.session import App
from server.sources.base import PaperSource
from server import wsserver
from server.wsserver import serve
from server.client import Client, HandshakeRefused

KNOWN_TITLE = "Evaluating large language models in theory of mind tasks"   # already in the corpus


class Script:
    """What the fake source will do on the next pull."""

    records = []
    delay = 0.0
    raises = None


class FakeSource(PaperSource):
    name = "test-fake"
    label = "Fake source"
    docs = "tests only"

    async def search(self, request):
        if Script.raises is not None:
            raise Script.raises
        for i, rec in enumerate(Script.records[:request.limit]):
            if Script.delay:
                await asyncio.sleep(Script.delay)
            yield rec


def paper(n, title=None, **kw):
    return {"source_id": f"F{n}", "title": title or f"A pulled paper number {n}",
            "authors": [f"Author {n}"], "year": 2024, "venue": "Test Venue",
            "url": f"https://example.org/{n}", "doi": f"10.9999/test.{n}",
            "citations": n, "citations_field": "fake.count", "type": "article",
            "references": [], "reference_count": None, **kw}


class ServerCase(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        sources.register(FakeSource)

    @classmethod
    def tearDownClass(cls):
        sources.REGISTRY.pop(FakeSource.name, None)

    async def asyncSetUp(self):
        Script.records, Script.delay, Script.raises = [paper(i) for i in range(1, 4)], 0.0, None
        self.tmp = tempfile.TemporaryDirectory()
        self.ingest = pathlib.Path(self.tmp.name)
        self.cfg = dataclasses.replace(
            Config(), host="127.0.0.1", port=0, ping_interval=30.0,
            ingest_dir_override=self.ingest)
        self.app = App(self.cfg)
        self.server = await serve(self.cfg, self.app.session)
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.close()
        self.server.close()
        await self.server.wait_closed()
        for _ in range(100):                  # let cancelled jobs close their files
            if self.app._running == 0:
                break
            await asyncio.sleep(0.02)
        self.tmp.cleanup()

    async def connect(self, **kw):
        c = await Client.connect("127.0.0.1", self.port, **kw)
        self.clients.append(c)
        return c

    async def pull(self, client, **params):
        """Start a pull and return its job id, ignoring events from earlier pulls."""
        await client.send({"type": "pull.start", "id": "p1", "params": {"source": "test-fake",
                                                                       **params}})
        ack, _ = await client.recv_until("ack")
        return ack["job"]

    def staged(self, job_id):
        path = self.ingest / f"{job_id}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def meta(self, job_id):
        return json.loads((self.ingest / f"{job_id}.meta.json").read_text())


class TestHandshake(ServerCase):
    async def test_unknown_origin_is_refused(self):
        with self.assertRaises(HandshakeRefused) as ctx:
            await self.connect(origin="https://evil.example")
        self.assertEqual(ctx.exception.status, 403)

    async def test_allowed_origin_connects(self):
        client = await self.connect(origin="http://localhost:5173")
        await client.send({"type": "ping", "id": 1})
        self.assertEqual((await client.recv())["type"], "pong")

    async def test_wrong_path_is_404(self):
        with self.assertRaises(HandshakeRefused) as ctx:
            await self.connect(path="/socket")
        self.assertEqual(ctx.exception.status, 404)

    async def test_token_is_required_when_configured(self):
        self.server.close()
        await self.server.wait_closed()
        self.cfg = dataclasses.replace(self.cfg, token="hunter2")
        self.server = await serve(self.cfg, App(self.cfg).session)
        self.port = self.server.sockets[0].getsockname()[1]
        with self.assertRaises(HandshakeRefused) as ctx:
            await self.connect()
        self.assertEqual(ctx.exception.status, 401)
        client = await self.connect(token="hunter2")
        await client.send({"type": "ping"})
        self.assertEqual((await client.recv())["type"], "pong")


class TestStalling(ServerCase):
    async def test_a_peer_that_stops_answering_is_closed(self):
        self.server.close()
        await self.server.wait_closed()
        self.cfg = dataclasses.replace(self.cfg, ping_interval=0.05, ping_timeout=0.05)
        self.app = App(self.cfg)
        self.server = await serve(self.cfg, self.app.session)
        self.port = self.server.sockets[0].getsockname()[1]

        client = await self.connect(answer_pings=False)
        with self.assertRaises(ConnectionError):
            await client.recv(timeout=5)

    async def test_a_silent_connection_is_not_held_open(self):
        original = wsserver.HANDSHAKE_TIMEOUT
        wsserver.HANDSHAKE_TIMEOUT = 0.05
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            self.assertIn(b"408", head.split(b"\r\n")[0])
            writer.close()
        finally:
            wsserver.HANDSHAKE_TIMEOUT = original


class TestBackpressure(unittest.IsolatedAsyncioTestCase):
    """The queue in front of a client is bounded; the heartbeat must survive that."""

    def connection(self, **kw):
        cfg = dataclasses.replace(Config(), **{"send_queue": 1, "ping_interval": 0.01,
                                               "ping_timeout": 0.01, **kw})
        return wsserver.WSConnection(FakeReader(), FakeWriter(), cfg, None)

    async def test_lossy_events_are_dropped_when_the_queue_is_full(self):
        conn = self.connection()
        self.assertTrue(conn.offer({"type": "job.progress"}))
        self.assertFalse(conn.offer({"type": "job.progress"}))
        self.assertEqual(conn.dropped, 1)

    async def test_control_frames_report_a_stuck_client(self):
        conn = self.connection()
        self.assertTrue(conn._control(b"one"))
        self.assertFalse(conn._control(b"two"))

    async def test_heartbeat_closes_a_client_that_stopped_reading(self):
        conn = self.connection()
        conn.offer({"type": "paper"})              # queue is now full, nothing draining it
        task = asyncio.create_task(conn._heartbeat())
        await asyncio.wait_for(conn.closed.wait(), 2)
        task.cancel()

    async def test_heartbeat_closes_a_client_that_stops_ponging(self):
        conn = self.connection(send_queue=8)
        task = asyncio.create_task(conn._heartbeat())
        await asyncio.wait_for(conn.closed.wait(), 2)
        task.cancel()

    async def test_sending_to_a_closed_connection_is_a_no_op(self):
        conn = self.connection()
        conn.closed.set()
        self.assertFalse(await conn.send({"type": "paper"}))
        self.assertFalse(conn.offer({"type": "paper"}))


class FakeReader:
    async def read(self, n):
        await asyncio.sleep(3600)


class FakeWriter:
    def __init__(self):
        self.written = bytearray()

    def write(self, data):
        self.written += data

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass

    def get_extra_info(self, key):
        return ("127.0.0.1", 0)


class TestCommands(ServerCase):
    async def test_hello_describes_the_server(self):
        client = await self.connect()
        await client.send({"type": "hello", "id": "h"})
        ev = await client.recv()
        self.assertEqual((ev["type"], ev["id"]), ("hello", "h"))
        self.assertEqual(ev["corpus"]["axes"], 28)
        self.assertIn("test-fake", [s["name"] for s in ev["sources"]])

    async def test_axes_carry_their_derived_query(self):
        client = await self.connect()
        await client.send({"type": "corpus.axes", "params": {"side": "machine"}})
        ev = await client.recv()
        axis = next(a for a in ev["axes"] if a["id"] == "tom-false-belief")
        self.assertIn("False-belief attribution", axis["query"])
        self.assertIn("large language model", axis["query"])

    async def test_unknown_command_is_named(self):
        client = await self.connect()
        await client.send({"type": "pull.everything", "id": 9})
        ev = await client.recv()
        self.assertEqual(ev["error"]["code"], "unknown_command")
        self.assertEqual(ev["id"], 9)

    async def test_bad_parameters_are_named(self):
        client = await self.connect()
        await client.send({"type": "pull.start", "id": 2, "params": {"axis": "telepathy"}})
        ev = await client.recv()
        self.assertEqual(ev["error"]["code"], "unknown_axis")

    async def test_garbage_frame_gets_an_error_not_a_disconnect(self):
        client = await self.connect()
        await client.send("not-an-object")
        ev = await client.recv()
        self.assertEqual(ev["error"]["code"], "bad_request")
        await client.send({"type": "ping", "id": "still-here"})
        self.assertEqual((await client.recv())["type"], "pong")


class TestPull(ServerCase):
    async def test_papers_stream_and_land_in_staging(self):
        client = await self.connect()
        job = await self.pull(client, query="anything", limit=10)
        started = await client.recv()
        self.assertEqual(started["type"], "job.started")
        self.assertEqual(started["staged_path"], f"{self.ingest}/{job}.jsonl")

        done, papers = await client.recv_until("job.done", collect=("paper",))
        self.assertEqual(len(papers), 3)
        self.assertEqual([p["record"]["title"] for p in papers],
                         [r["title"] for r in Script.records])
        self.assertTrue(all(p["dedup"]["status"] == "new" for p in papers))
        self.assertEqual(done["summary"]["new"], 3)
        self.assertEqual(done["summary"]["fetched"], 3)

        staged = self.staged(job)
        self.assertEqual(len(staged), 3)
        self.assertEqual(staged[0]["review"]["status"], "pending")
        self.assertEqual(staged[0]["provenance"]["source"], "test-fake")
        self.assertEqual(self.meta(job)["state"], "done")

    async def test_axis_pull_proposes_that_axis(self):
        client = await self.connect()
        job = await self.pull(client, axis="anchoring", limit=1)
        await client.recv_until("job.done")
        self.assertEqual(self.staged(job)[0]["review"]["proposed_axes"], ["anchoring"])

    async def test_papers_already_in_the_corpus_are_not_restaged(self):
        Script.records = [paper(1, title=KNOWN_TITLE), paper(2)]
        client = await self.connect()
        job = await self.pull(client, query="tom", limit=10)
        done, papers = await client.recv_until("job.done", collect=("paper",))
        self.assertEqual(len(papers), 1)
        self.assertEqual(done["summary"]["in_corpus"], 1)
        self.assertEqual(done["summary"]["new"], 1)
        self.assertEqual(len(self.staged(job)), 1)

    async def test_include_known_reports_the_skipped_ones(self):
        Script.records = [paper(1, title=KNOWN_TITLE)]
        client = await self.connect()
        await self.pull(client, query="tom", include_known=True)
        done, papers = await client.recv_until("job.done", collect=("paper",))
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["dedup"], {"status": "in_corpus", "matched": "kosinski2024",
                                              "reason": "title"})
        self.assertEqual(done["summary"]["new"], 0)

    async def test_repeats_within_one_pull_are_caught(self):
        Script.records = [paper(1), paper(1)]
        client = await self.connect()
        await self.pull(client, query="x")
        done, papers = await client.recv_until("job.done", collect=("paper",))
        self.assertEqual(len(papers), 1)
        self.assertEqual(done["summary"]["duplicate_in_run"], 1)

    async def test_a_second_pull_sees_what_the_first_one_staged(self):
        client = await self.connect()
        await self.pull(client, query="x")
        await client.recv_until("job.done")
        await self.pull(client, query="x")
        done, papers = await client.recv_until("job.done", collect=("paper",))
        self.assertEqual(papers, [])
        self.assertEqual(done["summary"]["already_staged"], 3)

    async def test_staging_can_be_turned_off(self):
        client = await self.connect()
        job = await self.pull(client, query="x", stage=False)
        done, papers = await client.recv_until("job.done", collect=("paper",))
        self.assertEqual(len(papers), 3)
        self.assertIsNone(done["staged_path"])
        self.assertFalse((self.ingest / f"{job}.jsonl").exists())

    async def test_upstream_failure_is_reported_with_its_wait(self):
        Script.raises = SourceRateLimited("OpenAlex budget is gone", retry_after=27072)
        client = await self.connect()
        job = await self.pull(client, query="x")
        ev, _ = await client.recv_until("job.failed")
        self.assertEqual(ev["error"]["code"], "upstream_rate_limited")
        self.assertEqual(ev["error"]["retry_after"], 27072)
        self.assertEqual(self.meta(job)["state"], "failed")

    async def test_cancel_stops_a_running_pull(self):
        Script.records = [paper(i) for i in range(1, 40)]
        Script.delay = 0.05
        client = await self.connect()
        job = await self.pull(client, query="x", limit=40)
        await client.recv_until("paper")
        await client.send({"type": "pull.cancel", "id": "c", "params": {"job": job}})
        ev, _ = await client.recv_until("job.cancelled", collect=("paper", "ack"))
        self.assertLess(ev["summary"]["fetched"], 40)
        self.assertEqual(self.meta(job)["state"], "cancelled")

    async def test_cancelling_an_unknown_job(self):
        client = await self.connect()
        await client.send({"type": "pull.cancel", "id": "c", "params": {"job": "job_9999"}})
        ev = await client.recv()
        self.assertEqual(ev["error"]["code"], "unknown_job")

    async def test_connection_limit_on_concurrent_pulls(self):
        Script.records = [paper(i) for i in range(1, 20)]
        Script.delay = 0.05
        client = await self.connect()
        for _ in range(self.cfg.max_jobs_per_conn):
            await self.pull(client, query="x", limit=20)
        await client.send({"type": "pull.start", "id": "over",
                           "params": {"source": "test-fake", "query": "x"}})
        ev, _ = await client.recv_until("error", collect=("paper", "job.started", "job.progress"))
        self.assertEqual(ev["error"]["code"], "too_many_jobs")

    async def test_jobs_list_reports_state(self):
        client = await self.connect()
        job = await self.pull(client, query="x")
        await client.recv_until("job.done")
        await client.send({"type": "jobs.list", "id": "j"})
        ev, _ = await client.recv_until("jobs")
        self.assertEqual([j["job"] for j in ev["jobs"]], [job])
        self.assertEqual(ev["jobs"][0]["state"], "done")

    async def test_dropping_the_connection_cancels_the_pull(self):
        Script.records = [paper(i) for i in range(1, 100)]
        Script.delay = 0.05
        client = await self.connect()
        await self.pull(client, query="x", limit=99)
        await client.recv_until("paper")
        await client.close()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if self.app._running == 0:
                break
        self.assertEqual(self.app._running, 0)


if __name__ == "__main__":
    unittest.main()
