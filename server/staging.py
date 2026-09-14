"""Where a pull lands on disk: data/ingest/, never data/sources.json.

One JSONL of candidates per job plus a sidecar meta file holding the query and
the counts. The review step (roadmap phase 2) reads these; nothing in this
backend promotes a candidate into the corpus.
"""
import json
import logging
import pathlib

HEADER = "candidates pulled by the ingestion backend; unreviewed"

log = logging.getLogger("simulxalive.staging")


class Staging:
    """Append-only candidate file for one job. Disabled staging is a no-op."""

    def __init__(self, ingest_dir, job_id, *, enabled=True, root=None):
        self.dir = pathlib.Path(ingest_dir)
        self.job_id = job_id
        self.enabled = enabled
        self.root = pathlib.Path(root) if root else None
        self.written = 0
        self._fh = None

    @property
    def path(self):
        return self.dir / f"{self.job_id}.jsonl"

    @property
    def meta_path(self):
        return self.dir / f"{self.job_id}.meta.json"

    def relpath(self, path=None):
        path = path or self.path
        if self.root:
            try:
                return str(path.relative_to(self.root))
            except ValueError:
                pass
        return str(path)

    def start(self, meta):
        if not self.enabled:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")
        self._write_meta({"$comment": HEADER, **meta, "state": "running"})
        return self.relpath()

    def write(self, record):
        if not self._fh:
            return
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()
        self.written += 1

    def finish(self, meta, summary, state):
        if not self.enabled:
            return None
        if self._fh:
            self._fh.close()
            self._fh = None
        self._write_meta({"$comment": HEADER, **meta, "state": state, "summary": summary})
        return self.relpath()

    def _write_meta(self, doc):
        try:
            self.meta_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        except OSError as e:
            # The candidates are already on their way to the client; losing the
            # sidecar must not turn a finished pull into a crash.
            log.warning("could not write %s: %s", self.meta_path, e)
