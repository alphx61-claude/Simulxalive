"""Paper input sockets: one contract for every way a source can arrive.

    from sockets import submit
    submit({"socket": "doi", "values": {"raw": "10.1073/pnas.2405460121"},
            "axes": ["prompt-invariance"], "domain": "machine",
            "submitted_by": "taran"})

`submit` is the whole layer. The CLI (tools/ingest.py) is a thin wrapper over
it, and the input sockets on the site will be another - one envelope shape,
one set of rules, one review gate, whatever the front end looks like.

To add a socket: copy tools/sockets/doi.py, change the class attributes, import
it below. The manifest, the routing and the CLI pick it up with no other edit.
"""
from datetime import date
from typing import Any, Dict, List, Mapping, Optional

from .core import (COMMON_FIELDS, DOMAINS, Draft, Field, ReferenceSocket, Socket,
                   SocketError, all_sockets, get, manifest, register, route)
from . import store

# Registration order is tie-break order for routing: strong identifiers first,
# the generic link fallback last, manual never auto-routed.
from . import doi, arxiv, openalex, consensus, link, manual  # noqa: E402,F401

__all__ = ["submit", "queue", "manifest", "accept", "reject", "SocketError",
           "Socket", "ReferenceSocket", "Draft", "Field", "register", "route", "get"]


def _clean_axes(raw: Any) -> List[str]:
    if not raw:
        return []
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    axes = [str(a).strip() for a in items if str(a).strip()]
    known = set(store.axis_ids())
    unknown = [a for a in axes if a not in known]
    if unknown:
        raise SocketError("unknown_axis",
                          "Not construct ids from data/axes.json: " + ", ".join(unknown),
                          unknown=unknown)
    return axes


def _clean_domain(raw: Any) -> Optional[str]:
    d = (str(raw).strip().lower() or None) if raw else None
    if d and d not in DOMAINS:
        raise SocketError("bad_domain", f"domain must be one of {', '.join(DOMAINS)}.",
                          got=d)
    return d


def submit(payload: Mapping[str, Any], allow_duplicate: bool = False) -> Dict[str, Any]:
    """Take a submission envelope, stage a draft in data/inbox.json.

    Raises SocketError on anything it refuses; the caller decides how to show
    that. Never writes to data/sources.json - see store.accept for the gate.
    """
    payload = dict(payload or {})
    values = dict(payload.get("values") or {})
    if payload.get("raw") and "raw" not in values:
        values["raw"] = payload["raw"]

    name = payload.get("socket")
    socket = get(name) if name else route(str(values.get("raw", "")))

    draft = socket.build(values)
    draft.axes = _clean_axes(payload.get("axes", values.get("axes")))
    draft.domain = _clean_domain(payload.get("domain", values.get("domain")))
    draft.note = str(payload.get("note", values.get("note", "")) or "").strip()

    dupe = store.duplicate_of(draft)
    if dupe and not allow_duplicate:
        where, existing = dupe
        raise SocketError("duplicate",
                          f"Already in the corpus as {where}:{existing}.",
                          where=where, existing=existing)

    warnings = []
    if draft.missing:
        warnings.append("Not citable yet - missing " + ", ".join(draft.missing) +
                        ". No resolver is installed, so these have to be supplied "
                        "by hand before this can be accepted.")
    if not draft.axes:
        warnings.append("No axis tagged. A paper that bears on nothing in the "
                        "taxonomy probably does not belong in the corpus.")
    if dupe:
        warnings.append(f"Duplicate of {dupe[0]}:{dupe[1]}, staged anyway.")

    row = draft.as_dict()
    row.update(status="pending", received=date.today().isoformat(),
               submitted_by=str(payload.get("submitted_by",
                                            values.get("submitted_by", "")) or "").strip(),
               warnings=warnings)

    inbox = store.load_inbox()
    inbox.setdefault("submissions", []).append(row)
    store.save_inbox(inbox)

    return {"ok": True, "status": "pending", "key": draft.key, "socket": socket.name,
            "draft": draft.as_dict(), "missing": draft.missing, "warnings": warnings}


def queue(status: Optional[str] = "pending") -> List[Dict[str, Any]]:
    """Submissions awaiting review, or all of them with status=None."""
    return store.submissions(status)


def accept(key: str, by: str, source_id: Optional[str] = None) -> Dict[str, Any]:
    return store.accept(key, by, source_id)


def reject(key: str, reason: str, by: str = "") -> Dict[str, Any]:
    return store.reject(key, reason, by)
