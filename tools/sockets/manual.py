"""Manual socket: a typed citation, for papers that carry no usable identifier.

Every bibliography field is required here. There is no identifier to dedupe on,
so the key is the normalised title - which is why two spellings of one title
will not collide and the review gate matters.
"""
from typing import Any, Mapping

from .core import CITATION_FIELDS, Draft, Socket, citation_inputs, coerce_field, register
from . import identifiers


@register
class ManualSocket(Socket):
    name = "manual"
    label = "Manual entry"
    help = "Type the citation. Use when nothing resolvable exists - a report, a thesis, a talk."
    example = "Kosinski, M. (2023). Evaluating large language models in theory of mind tasks. PNAS."
    fields = citation_inputs(required=True)

    def detect(self, raw: str) -> float:
        return 0.0                      # never routed automatically; always chosen

    def build(self, values: Mapping[str, Any]) -> Draft:
        vals = {f: coerce_field(f, self.required(values, f)) for f in CITATION_FIELDS}
        ident = identifiers.sniff(vals["url"])
        key = identifiers.key_for(ident) or f"title:{identifiers.normalise_title(vals['title'])}"
        return self.draft(key, ident=ident, **vals)
