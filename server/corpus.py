"""What we already have, and how a pulled record is matched against it.

Two jobs: read the existing corpus (data/axes.json, data/sources.json, anything
already staged in data/ingest/), and decide whether an incoming record is new.
The seed bibliography carries no DOIs, so title matching does most of the work;
DOI and upstream id are used when both sides have them.
"""
import json
import pathlib
import re
import unicodedata

MIN_TITLE_KEY = 10  # shorter normalised titles are too collision-prone to match on


def normalise_title(title):
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def normalise_doi(doi):
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    d = re.sub(r"^doi:\s*", "", d)
    return d.strip()


class Corpus:
    """The committed data files, read once per job."""

    def __init__(self, axes, sources, rubric=None, families=None):
        self.axes = axes
        self.sources = sources
        self.rubric = rubric or {}
        self.families = families or {}
        self._by_id = {a["id"]: a for a in axes}

    @classmethod
    def load(cls, data_dir):
        data_dir = pathlib.Path(data_dir)
        axes_doc = json.loads((data_dir / "axes.json").read_text())
        sources_doc = json.loads((data_dir / "sources.json").read_text())
        return cls(axes_doc["axes"], sources_doc["sources"],
                   axes_doc.get("rubric"), axes_doc.get("families"))

    def axis(self, axis_id):
        return self._by_id.get(axis_id)

    @property
    def axis_ids(self):
        return list(self._by_id)


class Verdict:
    __slots__ = ("status", "matched", "reason")

    def __init__(self, status, matched=None, reason=None):
        self.status, self.matched, self.reason = status, matched, reason

    @property
    def is_new(self):
        return self.status == "new"

    def payload(self):
        d = {"status": self.status}
        if self.matched:
            d["matched"] = self.matched
            d["reason"] = self.reason
        return d


_ORIGIN_STATUS = {"corpus": "in_corpus", "staged": "already_staged", "run": "duplicate_in_run"}


class DedupIndex:
    """Title / DOI / upstream-id lookup over everything we have seen before."""

    def __init__(self):
        self._titles = {}
        self._dois = {}
        self._ids = {}
        self.refs = set()

    def __len__(self):
        """How many distinct records the index can match against."""
        return len(self._titles) + len(self._dois) + len(self._ids)

    def add(self, *, ref, origin, title=None, doi=None, source_id=None):
        if ref:
            self.refs.add(ref)
        key = normalise_title(title)
        if len(key) >= MIN_TITLE_KEY:
            self._titles.setdefault(key, (ref, origin))
        d = normalise_doi(doi)
        if d:
            self._dois.setdefault(d, (ref, origin))
        if source_id:
            self._ids.setdefault(str(source_id), (ref, origin))

    def check(self, *, title=None, doi=None, source_id=None):
        for reason, table, key in (
            ("doi", self._dois, normalise_doi(doi)),
            ("source_id", self._ids, str(source_id) if source_id else ""),
            ("title", self._titles, normalise_title(title)),
        ):
            if reason == "title" and len(key) < MIN_TITLE_KEY:
                continue
            hit = table.get(key) if key else None
            if hit:
                ref, origin = hit
                return Verdict(_ORIGIN_STATUS[origin], ref, reason)
        return Verdict("new")

    @classmethod
    def from_corpus(cls, corpus):
        idx = cls()
        for sid, src in corpus.sources.items():
            idx.add(ref=sid, origin="corpus", title=src.get("title"), doi=src.get("doi"))
        return idx

    def add_staged(self, ingest_dir):
        """Index candidates pulled by earlier jobs so a repeat pull stays quiet."""
        ingest_dir = pathlib.Path(ingest_dir)
        if not ingest_dir.is_dir():
            return 0
        n = 0
        for path in sorted(ingest_dir.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                prov = rec.get("provenance") or {}
                self.add(ref=rec.get("proposed_id") or prov.get("source_id"), origin="staged",
                         title=rec.get("title"), doi=rec.get("doi"),
                         source_id=prov.get("source_id"))
                n += 1
        return n
