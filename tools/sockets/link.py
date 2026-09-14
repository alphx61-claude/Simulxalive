"""Generic link socket: the fallback for a publisher or repository page.

Deliberately low weight - if a DOI or an arXiv id is visible in the URL, the
socket that owns that identifier routes the paste instead.
"""
from .core import ReferenceSocket, register
from .identifiers import URL_RE


@register
class LinkSocket(ReferenceSocket):
    name = "link"
    kind = "url"
    label = "Link"
    help = "Any paper URL. Used only when no stronger identifier is present."
    example = "https://www.nature.com/articles/s41562-024-01882-z"
    patterns = (URL_RE,)
    weight = 0.2
    raw_label = "URL"
    raw_placeholder = "https://..."
