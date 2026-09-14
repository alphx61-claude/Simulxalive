"""Reading and writing the data files the socket layer touches.

Sockets never write to data/sources.json. They write drafts to data/inbox.json,
and a person moves a draft across with `accept` - the human review gate the
project decided on. Everything here is plain JSON on disk; there is no database
and Phase 3 ships the site as static files, so there should never be one.
"""
import json
import pathlib
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .core import SocketError
from . import identifiers

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
INBOX = DATA / "inbox.json"
SOURCES = DATA / "sources.json"
AXES = DATA / "axes.json"

INBOX_COMMENT = (
    "Staging queue for paper submissions. Sockets (tools/sockets, docs/SOCKETS.md) "
    "write here; nothing reaches data/sources.json until a person accepts it with "
    "tools/ingest.py accept. Drafts are not citations - a pending row may be missing "
    "everything but an identifier."
)


def _read(path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _write(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------- inbox
def load_inbox() -> Dict[str, Any]:
    if not INBOX.exists():
        return {"$comment": INBOX_COMMENT, "submissions": []}
    return _read(INBOX)


def save_inbox(inbox: Dict[str, Any]) -> None:
    inbox.setdefault("$comment", INBOX_COMMENT)
    _write(INBOX, inbox)


def submissions(status: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = load_inbox().get("submissions", [])
    return [r for r in rows if status in (None, r.get("status"))]


def find(key: str) -> Optional[Dict[str, Any]]:
    for r in submissions():
        if r["key"] == key or r.get("id") == key:
            return r
    return None


# ------------------------------------------------------------------- sources
def load_sources() -> Dict[str, Any]:
    return _read(SOURCES)


def axis_ids() -> List[str]:
    return [a["id"] for a in _read(AXES)["axes"]]


def source_keys() -> Dict[str, str]:
    """Dedupe index over the existing bibliography: key -> source id."""
    index = {}
    for sid, s in load_sources()["sources"].items():
        ident = identifiers.sniff(s.get("url", ""))
        for kind, value in ident.items():
            index.setdefault(f"{kind}:{value}", sid)
        if s.get("title"):
            index.setdefault(f"title:{identifiers.normalise_title(s['title'])}", sid)
    return index


def duplicate_of(draft) -> Optional[Tuple[str, str]]:
    """(where, id) if this paper is already known, else None."""
    candidates = {draft.key}
    for kind, value in draft.ident.items():
        candidates.add(f"{kind}:{value}")
    if draft.title:
        candidates.add(f"title:{identifiers.normalise_title(draft.title)}")

    index = source_keys()
    for c in candidates:
        if c in index:
            return "sources", index[c]
    for row in submissions():
        if row.get("status") == "rejected":
            continue
        known = {row["key"]} | {f"{k}:{v}" for k, v in row.get("ident", {}).items()}
        if row.get("title"):
            known.add(f"title:{identifiers.normalise_title(row['title'])}")
        if candidates & known:
            return "inbox", row["key"]
    return None


# ----------------------------------------------------------------------- ids
def slug(authors: str, year: int, taken) -> str:
    """Bibliography id in the house style: first author's surname plus year."""
    surname = re.split(r"[,\s]", (authors or "").strip())[0]
    surname = re.sub(r"[^a-z]", "", surname.lower()) or "anon"
    base = f"{surname}{year}"
    if base not in taken:
        return base
    for suffix in "bcdefghijkmnpqrstuvwxyz":
        if f"{base}{suffix}" not in taken:
            return f"{base}{suffix}"
    raise SocketError("slug_exhausted", f"Too many entries named {base}.")


# --------------------------------------------------------------- review gate
def accept(key: str, by: str, source_id: Optional[str] = None) -> Dict[str, Any]:
    """Move a pending draft into data/sources.json. Refuses an incomplete one."""
    inbox = load_inbox()
    row = next((r for r in inbox["submissions"] if r["key"] == key), None)
    if row is None:
        raise SocketError("not_found", f"No submission with key '{key}'.")
    if row["status"] != "pending":
        raise SocketError("not_pending", f"'{key}' is already {row['status']}.")

    missing = [f for f in ("title", "authors", "year", "venue", "url") if not row.get(f)]
    if missing:
        raise SocketError(
            "incomplete",
            "A bibliography entry needs every field. Missing: " + ", ".join(missing) +
            ". Supply them on the submission rather than guessing at them.",
            missing=missing)

    data = load_sources()
    sources = data["sources"]
    sid = source_id or slug(row["authors"], row["year"], sources)
    if sid in sources:
        raise SocketError("id_taken", f"Source id '{sid}' already exists.")

    entry = {"authors": row["authors"], "year": row["year"], "title": row["title"],
             "venue": row["venue"], "url": row["url"]}
    # Forward-compatible with the v2 paper record (docs/DATA-MODEL.md); the 61
    # seed entries do not carry these yet and are left untouched.
    if row.get("domain"):
        entry["domain"] = row["domain"]
    if row.get("axes"):
        entry["axes"] = row["axes"]
    entry["provenance"] = {"via": f"socket:{row['socket']}", "key": row["key"],
                           "submitted_by": row.get("submitted_by") or "unknown",
                           "accepted_by": by, "accepted": date.today().isoformat()}

    sources[sid] = entry
    _write(SOURCES, data)

    row.update(status="accepted", source_id=sid, accepted_by=by,
               accepted=date.today().isoformat())
    save_inbox(inbox)
    return {"ok": True, "status": "accepted", "key": key, "source_id": sid,
            "entry": entry}


def reject(key: str, reason: str, by: str = "") -> Dict[str, Any]:
    inbox = load_inbox()
    row = next((r for r in inbox["submissions"] if r["key"] == key), None)
    if row is None:
        raise SocketError("not_found", f"No submission with key '{key}'.")
    if row["status"] != "pending":
        raise SocketError("not_pending", f"'{key}' is already {row['status']}.")
    row.update(status="rejected", reason=reason, rejected_by=by,
               rejected=date.today().isoformat())
    save_inbox(inbox)
    return {"ok": True, "status": "rejected", "key": key, "reason": reason}
