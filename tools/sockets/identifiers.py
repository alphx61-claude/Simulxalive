"""Pure identifier parsing. No network, no guessing.

Every function returns a canonical string or None. `sniff` runs them all over
a raw paste, which is how a DOI hidden inside a publisher URL still gets found.
"""
import re
from typing import Dict, Optional
from urllib.parse import urlsplit, urlunsplit

# Shared with the browser via the socket manifest - keep them ECMAScript-safe.
DOI_RE = r"10\.\d{4,9}/[^\s\"'<>,;]+"
ARXIV_NEW_RE = r"\b(\d{4}\.\d{4,5})(v\d+)?\b"
ARXIV_OLD_RE = r"\b([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?\b"
OPENALEX_RE = r"\b(W\d{6,12})\b"
CONSENSUS_RE = r"consensus\.app/papers/details/([0-9a-f]{8,})"
URL_RE = r"https?://[^\s\"'<>]+"

_TRAILING = ".,;:)]}>"


def parse_doi(raw: str) -> Optional[str]:
    m = re.search(DOI_RE, raw or "", re.I)
    if not m:
        return None
    return m.group(0).rstrip(_TRAILING).lower()


def parse_arxiv(raw: str) -> Optional[str]:
    raw = raw or ""
    # A DOI can contain a digit run that looks like an arXiv id; ignore those.
    if re.search(r"arxiv\.org/(abs|pdf)/", raw, re.I) or re.search(r"arxiv:", raw, re.I) \
            or not parse_doi(raw):
        for pattern in (ARXIV_NEW_RE, ARXIV_OLD_RE):
            m = re.search(pattern, raw)
            if m:
                return m.group(1)
    return None


def parse_openalex(raw: str) -> Optional[str]:
    m = re.search(OPENALEX_RE, raw or "")
    return m.group(1).upper() if m else None


def parse_consensus(raw: str) -> Optional[str]:
    m = re.search(CONSENSUS_RE, raw or "", re.I)
    return m.group(1).lower() if m else None


def parse_url(raw: str) -> Optional[str]:
    m = re.search(URL_RE, raw or "")
    return normalise_url(m.group(0).rstrip(_TRAILING)) if m else None


def normalise_url(url: str) -> str:
    """Lowercase scheme and host, drop tracking query and fragment.

    Consensus links arrive with `?utm_source=...`; two links to one paper must
    produce one dedupe key.
    """
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, "", ""))


def sniff(raw: str) -> Dict[str, str]:
    """Every identifier visible in a raw reference, canonicalised."""
    found = {}
    for name, fn in (("doi", parse_doi), ("arxiv", parse_arxiv),
                     ("openalex", parse_openalex), ("consensus", parse_consensus),
                     ("url", parse_url)):
        v = fn(raw)
        if v:
            found[name] = v
    return found


def key_for(ident: Dict[str, str]) -> Optional[str]:
    """The dedupe key: the strongest identifier present, as 'kind:value'."""
    for kind in ("doi", "arxiv", "openalex", "consensus", "url"):
        if ident.get(kind):
            return f"{kind}:{ident[kind]}"
    return None


def normalise_title(title: str) -> str:
    """Title reduced for comparison only - never written back to a record."""
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
