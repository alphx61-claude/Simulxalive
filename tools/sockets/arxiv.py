"""arXiv socket. Preprints, which this corpus carries a lot of."""
from .core import ReferenceSocket, register


@register
class ArxivSocket(ReferenceSocket):
    name = "arxiv"
    kind = "arxiv"
    label = "arXiv"
    help = ("An arXiv id or abs/pdf link. Versions are stripped: 2303.11436v2 and "
            "2303.11436 are the same paper.")
    example = "arXiv:2303.11436"
    patterns = (r"arxiv\.org/(abs|pdf)/", r"arxiv:\s*\d{4}\.\d{4,5}")
    raw_label = "arXiv id or link"
    raw_placeholder = "arXiv:2303.11436"

    def canonical_url(self, ident):
        return f"https://arxiv.org/abs/{ident['arxiv']}"
