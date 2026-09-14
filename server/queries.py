"""Discovery queries, derived from the taxonomy rather than typed by hand.

An axis in data/axes.json already names its instrument - "Sally-Anne and
unexpected-contents batteries, with true-belief controls" - which is most of a
literature search. Build the query from the label plus the distinctive words of
the instrument, and let the caller override it outright when the derived query
is wrong. A query string is not a finding, so deriving one breaks no invariant.
"""
import re

SIDE_TERMS = {
    "machine": "large language model",
    "human": "human participants",
    "bridge": "large language model human comparison",
    "any": "",
}

# Words that describe how a study was run rather than what it studied. They cost
# precision in a search engine that scores on term overlap.
GENERIC = {
    "task", "tasks", "battery", "batteries", "test", "tests", "testing", "control",
    "controls", "version", "versions", "item", "items", "trial", "trials", "study",
    "studies", "protocol", "protocols", "measure", "measures", "scale", "scales",
    "paradigm", "paradigms", "standard", "classic", "classical", "variant", "variants",
    "and", "or", "with", "without", "the", "a", "an", "of", "on", "in", "for", "to",
    "from", "by", "at", "as", "plus", "per", "against", "over", "under", "into",
    "matched", "paired", "same", "both", "each", "their", "its",
}

MAX_INSTRUMENT_TERMS = 6


def instrument_terms(instrument, exclude=(), limit=MAX_INSTRUMENT_TERMS):
    """The distinctive words of an instrument description, in order, deduplicated."""
    seen, out = set(exclude), []
    for word in re.split(r"[^a-z0-9]+", (instrument or "").lower()):
        if len(word) < 3 or word in GENERIC or word in seen:
            continue
        seen.add(word)
        out.append(word)
        if len(out) >= limit:
            break
    return out


def axis_query(axis, side="any", limit=MAX_INSTRUMENT_TERMS):
    """The discovery query for one axis. Deterministic: same axis, same string."""
    label = (axis.get("label") or "").strip()
    used = {w for w in re.split(r"[^a-z0-9]+", label.lower()) if w}
    terms = [label] + instrument_terms(axis.get("instrument"), exclude=used, limit=limit)
    side_term = SIDE_TERMS.get(side, "")
    if side_term:
        terms.append(side_term)
    return " ".join(t for t in terms if t)


def describe_axes(corpus, side="any"):
    """Axis list for a client picking what to pull."""
    return [{
        "id": a["id"],
        "label": a.get("label"),
        "family": a.get("family"),
        "evidence": a.get("evidence"),
        "sources": len(a.get("sources") or []),
        "query": axis_query(a, side),
    } for a in corpus.axes]
