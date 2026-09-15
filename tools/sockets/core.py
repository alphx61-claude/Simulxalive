"""The socket contract: one small interface every paper input implements.

A socket turns one kind of raw paper reference - a DOI, an arXiv id, a
Consensus link, a hand-typed citation - into a normalised draft record. Each
socket declares its own input fields and its own detection patterns, so a form
can be *rendered from the registry* instead of hand-written per socket, and so
a browser can route a paste the same way Python does. See docs/SOCKETS.md.

Two rules this module exists to enforce:

  * Nothing here touches the network. Identifier parsing is pure string work.
  * Nothing here invents metadata. A field the submitter did not supply and no
    resolver returned stays null and is listed under `missing`; a draft with
    anything missing cannot be accepted into the bibliography.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

# A bibliography entry is only citable when all five are known. Mirrors the
# shape of every entry in data/sources.json.
CITATION_FIELDS = ("title", "authors", "year", "venue", "url")

DOMAINS = ("human", "machine", "bridge")  # docs/DATA-MODEL.md


class SocketError(ValueError):
    """A submission the layer refuses. `code` is stable; `message` is for people."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra

    def as_dict(self):
        return {"code": self.code, "message": self.message, **self.extra}


# ----------------------------------------------------------------- field spec
@dataclass(frozen=True)
class Field:
    """One input a socket asks for. The future web form renders from these."""
    name: str
    label: str
    kind: str = "text"          # text | textarea | number | select | multiselect
    required: bool = False
    placeholder: str = ""
    help: str = ""
    options: Tuple[str, ...] = ()

    STRUCTURAL = ("name", "label", "kind", "required")

    def as_dict(self):
        """The four structural keys always; placeholder, help and options only when set."""
        d = {**asdict(self), "options": list(self.options)}
        return {k: v for k, v in d.items() if k in self.STRUCTURAL or v}


# Asked on every socket: what the paper bears on, and who is vouching for it.
# `axes` is validated against data/axes.json at submit time.
COMMON_FIELDS: Tuple[Field, ...] = (
    Field("axes", "Axes", "multiselect",
          help="Construct ids from data/axes.json this paper bears on."),
    Field("domain", "Domain", "select", options=DOMAINS,
          help="human, machine, or bridge - a bridge paper measures both sides."),
    Field("note", "Note", "textarea",
          help="Why this belongs. Free text; never a number the paper does not report."),
    Field("submitted_by", "Submitted by",
          help="Who is putting this forward. Recorded in provenance."),
)


# --------------------------------------------------------------------- draft
@dataclass
class Draft:
    """A normalised, not-yet-accepted paper record."""
    key: str                                   # canonical dedupe key, "doi:10.1038/x"
    socket: str
    ident: Dict[str, str] = field(default_factory=dict)
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    venue: Optional[str] = None
    url: Optional[str] = None
    axes: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    note: str = ""

    @property
    def missing(self) -> List[str]:
        return [f for f in CITATION_FIELDS if not getattr(self, f)]

    @property
    def citable(self) -> bool:
        return not self.missing

    def as_dict(self):
        return asdict(self)      # field order is the record order; see the class body


# -------------------------------------------------------------------- socket
class Socket:
    """Subclass, set the class attributes, implement build(). Then register it.

    `patterns` are plain regexes shared with the browser, so keep them
    ECMAScript-compatible: no named groups, no lookbehind.
    """
    name = ""
    label = ""
    help = ""
    example = ""
    patterns: Tuple[str, ...] = ()
    weight = 1.0                      # detection confidence when a pattern hits
    fields: Tuple[Field, ...] = ()

    def detect(self, raw: str) -> float:
        """0 = not mine, 1 = certainly mine. Highest score routes the paste."""
        raw = (raw or "").strip()
        return self.weight if any(re.search(p, raw, re.I) for p in self.patterns) else 0.0

    def build(self, values: Mapping[str, Any]) -> Draft:
        raise NotImplementedError

    # helpers for subclasses -------------------------------------------------
    def draft(self, key: str, **kw) -> Draft:
        return Draft(key=key, socket=self.name, **kw)

    def required(self, values: Mapping[str, Any], name: str) -> str:
        v = str(values.get(name, "") or "").strip()
        if not v:
            raise SocketError("field_missing", f"{self.name}: '{name}' is required.",
                              field=name)
        return v

    def as_dict(self):
        return {"name": self.name, "label": self.label, "help": self.help,
                "example": self.example, "patterns": list(self.patterns),
                "weight": self.weight,
                "fields": [f.as_dict() for f in self.fields]}


# ------------------------------------------------------------------ registry
_REGISTRY: "Dict[str, Socket]" = {}


def register(cls):
    """Class decorator. One socket per module; import it in __init__ to enable."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} needs a name")
    _REGISTRY[cls.name] = cls()
    return cls


def get(name: str) -> Socket:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise SocketError("unknown_socket", f"No socket named '{name}'.",
                          known=sorted(_REGISTRY))


def all_sockets() -> List[Socket]:
    return list(_REGISTRY.values())


def route(raw: str) -> Socket:
    """Pick the socket for a raw paste. Ties break toward registration order."""
    scored = [(s.detect(raw), -i, s) for i, s in enumerate(all_sockets())]
    score, _, best = max(scored)
    if score <= 0:
        raise SocketError("unroutable",
                          "Nothing recognised that reference. Use the manual socket, "
                          "or name a socket explicitly.",
                          known=sorted(_REGISTRY))
    return best


def manifest() -> Dict[str, Any]:
    """Everything a front-end needs to render the inputs and route a paste."""
    return {"common": [f.as_dict() for f in COMMON_FIELDS],
            "domains": list(DOMAINS),
            "citation_fields": list(CITATION_FIELDS),
            "sockets": [s.as_dict() for s in all_sockets()]}


# Offered by every socket: the five bibliography fields, typed by hand. With no
# resolver installed (see resolve.py) this is the only way a draft becomes
# citable - which is the point. Nothing fills these in on a submitter's behalf.
def citation_inputs(required: bool = False) -> Tuple[Field, ...]:
    return (
        Field("title", "Title", required=required,
              help="Exactly as published."),
        Field("authors", "Authors", required=required,
              placeholder="Surname, A. B. et al.",
              help="House style: first author, then 'et al.'"),
        Field("year", "Year", "number", required=required),
        Field("venue", "Venue", required=required,
              placeholder="Nature Human Behaviour",
              help="Journal, conference or 'arXiv'."),
        Field("url", "URL", required=required,
              help="Resolves to the paper record. Left blank, the identifier's "
                   "canonical link is used."),
    )


class ReferenceSocket(Socket):
    """Base for every socket whose input is an identifier or a link.

    Parses the identifier, asks the active resolver for metadata, then lets any
    hand-typed field win over the resolver. Subclasses set `kind`, `patterns`
    and the labels; most need nothing else.
    """
    kind = ""                    # identifier kind from identifiers.sniff()
    raw_label = "Reference"
    raw_placeholder = ""

    @property
    def fields(self):
        return (Field("raw", self.raw_label, required=True,
                      placeholder=self.raw_placeholder,
                      help="Pasted whole - a bare id or a full link both work."),
                ) + citation_inputs()

    def canonical_url(self, ident: Mapping[str, str]) -> Optional[str]:
        """The identifier's own resolver link. Derived, never invented."""
        return ident.get("url")

    def build(self, values: Mapping[str, Any]) -> Draft:
        from . import identifiers, resolve

        raw = self.required(values, "raw")
        ident = identifiers.sniff(raw)
        if self.kind and self.kind not in ident:
            raise SocketError("parse_failed",
                              f"{self.label}: no {self.kind} found in that reference.",
                              raw=raw)
        key = f"{self.kind}:{ident[self.kind]}" if self.kind else identifiers.key_for(ident)
        if not key:
            raise SocketError("parse_failed", f"{self.label}: nothing identifiable there.",
                              raw=raw)

        d = self.draft(key, ident=ident, url=self.canonical_url(ident))
        for k, v in resolve.resolve(ident).items():     # resolver, if installed
            setattr(d, k, v)
        for f in CITATION_FIELDS:                       # a human's typing wins
            v = values.get(f)
            if v not in (None, ""):
                setattr(d, f, coerce_field(f, v))
        return d


def coerce_field(name: str, value: Any) -> Any:
    if name == "year":
        try:
            return int(str(value).strip())
        except ValueError:
            raise SocketError("bad_field", f"'year' must be a number, got {value!r}.",
                              field="year")
    if name == "url":
        from . import identifiers
        return identifiers.normalise_url(str(value).strip())
    return str(value).strip()
