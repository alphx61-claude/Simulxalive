"""Turning an upstream record into a candidate the review gate can act on.

A candidate is not a paper. Everything that is a human judgement under
docs/DATA-MODEL.md - domain, major, cluster, which axes a paper actually bears
on - stays null or proposed here, and the citation count travels with the date
and the upstream field it came from so it can never be quoted as a bare number.
"""
import datetime
import re
import unicodedata

VIA = "ingest"


def _ascii(text):
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def surname(authors):
    """Best-effort family name of the first author, for the id proposal."""
    if not authors:
        return "anon"
    first = authors[0]
    if isinstance(first, dict):
        first = first.get("family") or first.get("name") or ""
    first = _ascii(first).strip()
    if "," in first:                       # "Kosinski, M."
        last = first.split(",")[0]
    else:                                  # "Michal Kosinski"
        last = first.split()[-1] if first.split() else ""
    last = re.sub(r"[^A-Za-z]", "", last).lower()
    return last or "anon"


_STOP = {"the", "a", "an", "of", "on", "in", "and", "for", "to", "is", "are", "with", "from"}


def propose_id(mapped, taken):
    """A stable-looking slug in the style of the seed bibliography (kosinski2024).

    Only a proposal: the reviewer renames it if they disagree.
    """
    base = surname(mapped.get("authors")) + (str(mapped.get("year")) if mapped.get("year") else "")
    if base not in taken:
        return base
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", _ascii(mapped.get("title", "")).lower()).split()
             if w not in _STOP]
    if words:
        with_word = base + words[0]
        if with_word not in taken:
            return with_word
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def candidate(mapped, *, source, query, job_id, fetched_at=None, taken=()):
    """Build the staged record. `mapped` is an adapter's normalised output."""
    fetched_at = fetched_at or datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    citations = None
    if mapped.get("citations") is not None:
        citations = {
            "value": mapped["citations"],
            "as_of": fetched_at[:10],
            "field": mapped.get("citations_field"),
        }
    return {
        "kind": "candidate",
        "proposed_id": propose_id(mapped, set(taken)),
        "title": mapped.get("title"),
        "authors": mapped.get("authors") or [],
        "year": mapped.get("year"),
        "venue": mapped.get("venue"),
        "url": mapped.get("url"),
        "doi": mapped.get("doi"),
        "type": mapped.get("type"),
        "citations": citations,
        "references": mapped.get("references") or [],
        "reference_count": mapped.get("reference_count"),
        # Judgements the machine does not get to make. Phase 2's review step fills these.
        "review": {
            "status": "pending",
            "proposed_axes": list(query.get("axes") or []),
            "domain": None,
            "major": None,
            "cluster": None,
        },
        "provenance": {
            "via": VIA,
            "source": source,
            "source_id": mapped.get("source_id"),
            "query": dict(query),
            "job": job_id,
            "fetched_at": fetched_at,
            "accepted_by": None,
        },
    }
