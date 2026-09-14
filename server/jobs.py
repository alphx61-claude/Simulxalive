"""A pull: ask one source for papers on one axis, stream what comes back.

The loop is deliberately boring - fetch, map, dedup, stage, emit - because the
interesting decisions are elsewhere: adapters own the upstream shape, corpus.py
owns what counts as already known, and records.py owns what a machine is allowed
to assert about a paper.
"""
import asyncio
import datetime
import logging
import time

from . import records
from .corpus import DedupIndex
from .errors import BackendError
from .queries import axis_query
from .sources.base import SearchRequest
from .staging import Staging

log = logging.getLogger("simulxalive.job")

PROGRESS_EVERY = 10

PENDING, RUNNING, DONE, FAILED, CANCELLED = "pending", "running", "done", "failed", "cancelled"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class PullJob:
    """One streaming pull. Owns its counters, its staging file and its lifecycle."""

    def __init__(self, job_id, params, *, cfg, corpus, fetcher, source_cls, emitter):
        self.id = job_id
        self.params = params
        self.cfg = cfg
        self.corpus = corpus
        self.source = source_cls(fetcher, cfg)
        self.emitter = emitter
        self.state = PENDING
        self.started_at = None
        self.error = None
        self.counts = {"fetched": 0, "new": 0, "in_corpus": 0, "already_staged": 0,
                       "duplicate_in_run": 0}
        self.staging = Staging(cfg.ingest_dir, job_id,
                               enabled=params.get("stage", cfg.stage), root=cfg.root)

    # ------------------------------------------------------------------ view
    @property
    def query(self):
        if self.params.get("query"):
            return self.params["query"]
        axis = self.corpus.axis(self.params["axis"])
        return axis_query(axis, self.params.get("side", "any"))

    def meta(self):
        return {"job": self.id, "source": self.source.name, "query": self.query,
                "params": self.params, "started_at": self.started_at}

    def snapshot(self):
        return {"job": self.id, "state": self.state, "source": self.source.name,
                "query": self.query, "counts": dict(self.counts),
                "started_at": self.started_at,
                "staged": self.staging.relpath() if self.staging.enabled else None}

    def summary(self, elapsed):
        return {**self.counts, "elapsed_s": round(elapsed, 2),
                "staged": self.staging.written,
                "staged_path": self.staging.relpath() if self.staging.enabled else None}

    # ------------------------------------------------------------------- run
    async def run(self):
        self.state, self.started_at = RUNNING, now()
        began = time.monotonic()
        index = await asyncio.to_thread(self._build_index)
        taken = set(self.corpus.sources) | index.refs   # slugs already spoken for

        staged_path = self.staging.start(self.meta())
        await self.emitter.send({"type": "job.started", "job": self.id,
                                 "source": self.source.name, "query": self.query,
                                 "params": self.params, "staged_path": staged_path,
                                 "known_keys": len(index)})
        request = SearchRequest(
            query=self.query,
            from_year=self.params.get("from_year"),
            to_year=self.params.get("to_year"),
            limit=self.params["limit"],
            per_page=self.params["per_page"],
            open_access_only=self.params.get("open_access", False),
        )

        try:
            async for mapped in self.source.search(request):
                self.counts["fetched"] += 1
                verdict = index.check(title=mapped.get("title"), doi=mapped.get("doi"),
                                      source_id=mapped.get("source_id"))
                if verdict.is_new:
                    record = records.candidate(
                        mapped, source=self.source.name, job_id=self.id, taken=taken,
                        query={"axes": [self.params["axis"]] if self.params.get("axis") else [],
                               "q": self.query, "from_year": self.params.get("from_year"),
                               "to_year": self.params.get("to_year")})
                    taken.add(record["proposed_id"])
                    index.add(ref=record["proposed_id"], origin="run",
                              title=record["title"], doi=record["doi"],
                              source_id=mapped.get("source_id"))
                    self.staging.write(record)
                    self.counts["new"] += 1
                    await self.emitter.send({"type": "paper", "job": self.id,
                                             "seq": self.counts["new"],
                                             "dedup": verdict.payload(), "record": record})
                else:
                    self.counts[verdict.status] += 1
                    if self.params.get("include_known"):
                        await self.emitter.send({
                            "type": "paper", "job": self.id, "seq": None,
                            "dedup": verdict.payload(),
                            "record": {"title": mapped.get("title"), "year": mapped.get("year"),
                                       "doi": mapped.get("doi"),
                                       "source_id": mapped.get("source_id")}})
                if self.counts["fetched"] % PROGRESS_EVERY == 0:
                    self.emitter.offer({"type": "job.progress", "job": self.id,
                                        **self.counts})
        except asyncio.CancelledError:
            self.state = CANCELLED
            summary = self.summary(time.monotonic() - began)
            self.staging.finish(self.meta(), summary, CANCELLED)
            self.emitter.offer({"type": "job.cancelled", "job": self.id, "summary": summary})
            raise
        except BackendError as e:
            self.state, self.error = FAILED, e.payload()
            summary = self.summary(time.monotonic() - began)
            self.staging.finish(self.meta(), {**summary, "error": self.error}, FAILED)
            await self.emitter.send({"type": "job.failed", "job": self.id,
                                     "error": self.error, "summary": summary})
            return
        except Exception as e:                                   # pragma: no cover - guard rail
            log.exception("job %s crashed", self.id)
            self.state = FAILED
            self.error = {"code": "internal_error", "message": str(e)}
            summary = self.summary(time.monotonic() - began)
            self.staging.finish(self.meta(), {**summary, "error": self.error}, FAILED)
            await self.emitter.send({"type": "job.failed", "job": self.id,
                                     "error": self.error, "summary": summary})
            return

        self.state = DONE
        summary = self.summary(time.monotonic() - began)
        path = self.staging.finish(self.meta(), summary, DONE)
        await self.emitter.send({"type": "job.done", "job": self.id, "summary": summary,
                                 "staged_path": path})

    def _build_index(self):
        index = DedupIndex.from_corpus(self.corpus)
        index.add_staged(self.cfg.ingest_dir)
        return index
