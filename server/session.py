"""Per-connection state: dispatch commands, own the jobs that connection started.

A session never outlives its socket. When the client goes away its jobs are
cancelled - a pull nobody is listening to is upstream load for nothing.
"""
import asyncio
import logging

from . import protocol, sources
from .corpus import Corpus
from .errors import BackendError, ProtocolError, TooManyJobs, UnknownJob
from .jobs import PullJob
from .queries import describe_axes
from .sources.http import Fetcher

log = logging.getLogger("simulxalive.session")


class App:
    """Process-wide state shared by every connection."""

    def __init__(self, cfg, corpus=None, fetcher=None, version="0.1.0"):
        self.cfg = cfg
        self.corpus = corpus or Corpus.load(cfg.data_dir)
        self.fetcher = fetcher or Fetcher(cfg)
        self.version = version
        self._running = 0
        self._counter = 0

    def next_job_id(self):
        self._counter += 1
        return f"job_{self._counter:04d}"

    def take_slot(self):
        if self._running >= self.cfg.max_jobs_total:
            return False
        self._running += 1
        return True

    def free_slot(self):
        self._running = max(0, self._running - 1)

    def session(self, conn):
        return Session(conn, self)


class Emitter:
    """How a job talks to its client: `send` waits for room, `offer` may drop."""

    def __init__(self, conn):
        self.conn = conn

    async def send(self, ev):
        await self.conn.send(_stamp(ev))

    def offer(self, ev):
        return self.conn.offer(_stamp(ev))


def _stamp(ev):
    return ev if "ts" in ev else {**ev, "ts": protocol.now()}


class Session:
    def __init__(self, conn, app):
        self.conn = conn
        self.app = app
        self.cfg = app.cfg
        self.jobs = {}
        self.tasks = {}

    # --------------------------------------------------------------- dispatch
    async def handle(self, conn, text):
        request_id = None
        try:
            type_, request_id, params = protocol.parse(text)
            await self._dispatch(type_, request_id, params)
        except BackendError as e:
            await conn.send(protocol.error_event(
                e, e.request_id if e.request_id is not None else request_id))
        except asyncio.CancelledError:
            raise
        except Exception:                                  # pragma: no cover - guard rail
            log.exception("command failed")
            await conn.send(protocol.event(
                "error", id=request_id,
                error={"code": "internal_error", "message": "the server failed to handle that"}))

    async def _dispatch(self, type_, request_id, params):
        if type_ == "hello":
            await self._reply(request_id, protocol.event(
                "hello", **protocol.hello(self.cfg, self.app.corpus, self.app.version)))
        elif type_ == "ping":
            await self._reply(request_id, protocol.event("pong"))
        elif type_ == "sources.list":
            await self._reply(request_id, protocol.event("sources", sources=sources.describe()))
        elif type_ == "corpus.axes":
            side = params.get("side", "any")
            if side not in protocol.SIDES:
                raise ProtocolError(f"'side' must be one of {', '.join(protocol.SIDES)}")
            await self._reply(request_id, protocol.event(
                "axes", side=side, axes=describe_axes(self.app.corpus, side)))
        elif type_ == "jobs.list":
            await self._reply(request_id, protocol.event(
                "jobs", jobs=[j.snapshot() for j in self.jobs.values()]))
        elif type_ == "pull.start":
            await self._start(request_id, params)
        elif type_ == "pull.cancel":
            await self._cancel(request_id, params)

    async def _reply(self, request_id, ev):
        if request_id is not None:
            ev = {**ev, "id": request_id}
        await self.conn.send(ev)

    # ------------------------------------------------------------------ pulls
    async def _start(self, request_id, params):
        resolved = protocol.validate_pull(params, self.cfg, self.app.corpus)
        live = sum(1 for t in self.tasks.values() if not t.done())
        if live >= self.cfg.max_jobs_per_conn:
            raise TooManyJobs(f"this connection already has {live} pulls running",
                              detail={"max": self.cfg.max_jobs_per_conn})
        if not self.app.take_slot():
            raise TooManyJobs("the server is at its pull limit; try again shortly",
                              detail={"max": self.cfg.max_jobs_total})

        job_id = self.app.next_job_id()
        try:
            job = PullJob(job_id, resolved, cfg=self.cfg, corpus=self.app.corpus,
                          fetcher=self.app.fetcher, source_cls=sources.get(resolved["source"]),
                          emitter=Emitter(self.conn))
            self.jobs[job_id] = job
            await self._reply(request_id, protocol.event("ack", command="pull.start", job=job_id))
        except BaseException:
            self.app.free_slot()
            raise
        self.tasks[job_id] = asyncio.create_task(self._run(job), name=job_id)

    async def _run(self, job):
        try:
            await job.run()
        except asyncio.CancelledError:
            log.info("job %s cancelled", job.id)
        finally:
            self.app.free_slot()

    async def _cancel(self, request_id, params):
        job_id = params.get("job")
        task = self.tasks.get(job_id)
        if task is None:
            raise UnknownJob(f"no job {job_id!r} on this connection",
                             detail={"jobs": list(self.tasks)})
        if task.done():
            await self._reply(request_id, protocol.event(
                "ack", command="pull.cancel", job=job_id, note="already finished"))
            return
        task.cancel()
        await self._reply(request_id, protocol.event("ack", command="pull.cancel", job=job_id))

    # ------------------------------------------------------------------ close
    async def aclose(self):
        live = [t for t in self.tasks.values() if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)
