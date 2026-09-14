"""OpenAlex socket. The id the Phase 2 ingestion adapter will speak natively."""
from .core import ReferenceSocket, register


@register
class OpenAlexSocket(ReferenceSocket):
    name = "openalex"
    kind = "openalex"
    label = "OpenAlex"
    help = "An OpenAlex work id. Carries citation counts and reference edges once Phase 2 lands."
    example = "W2741809807"
    patterns = (r"openalex\.org/W\d{6,12}", r"^\s*W\d{6,12}\s*$")
    raw_label = "OpenAlex work id"
    raw_placeholder = "W2741809807"

    def canonical_url(self, ident):
        return f"https://openalex.org/{ident['openalex']}"
