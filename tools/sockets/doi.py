"""DOI socket. The strongest identifier a paper can arrive with."""
from .core import ReferenceSocket, register
from .identifiers import DOI_RE


@register
class DoiSocket(ReferenceSocket):
    name = "doi"
    kind = "doi"
    label = "DOI"
    help = "A DOI, bare or as a doi.org link. Anything else in the paste is ignored."
    example = "10.1038/s41562-024-01882-z"
    patterns = (DOI_RE,)
    raw_label = "DOI"
    raw_placeholder = "10.1038/s41562-024-01882-z"

    def canonical_url(self, ident):
        return f"https://doi.org/{ident['doi']}"
