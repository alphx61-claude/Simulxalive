"""The metadata-resolution seam.

This layer deliberately ships with a resolver that returns nothing. Sockets
normalise what a human handed them; filling in title/authors/year/venue from an
identifier is a *network* job and belongs to the Phase 2 OpenAlex adapter, which
installs itself here:

    from sockets import resolve
    resolve.use(OpenAlexResolver())

Until then an unresolved draft is honest about it: the fields stay null and the
draft cannot be accepted. That is the ground rule - never invent a citation -
expressed as code rather than as a warning in a doc.
"""
from typing import Any, Dict, Optional

RESOLVABLE = ("title", "authors", "year", "venue", "url")


class Resolver:
    """Return bibliographic fields for an identifier, or None if unknown.

    Implementations must return only fields they actually retrieved, and must
    never fabricate a value to fill a gap.
    """
    name = "null"

    def resolve(self, ident: Dict[str, str]) -> Optional[Dict[str, Any]]:
        return None


_active = Resolver()


def use(resolver: Resolver) -> None:
    global _active
    _active = resolver


def active() -> Resolver:
    return _active


def resolve(ident: Dict[str, str]) -> Dict[str, Any]:
    """Fields the active resolver knows for `ident`. Unknown keys are dropped."""
    got = _active.resolve(ident) or {}
    out = {k: got[k] for k in RESOLVABLE if got.get(k)}
    if "year" in out:
        try:
            out["year"] = int(out["year"])
        except (TypeError, ValueError):
            del out["year"]
    return out
