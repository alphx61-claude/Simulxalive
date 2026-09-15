"""Consensus socket. How all 61 seed sources entered the bibliography."""
from .core import ReferenceSocket, register
from .identifiers import CONSENSUS_RE


@register
class ConsensusSocket(ReferenceSocket):
    name = "consensus"
    kind = "consensus"
    label = "Consensus link"
    help = ("A consensus.app paper link. Tracking query strings are stripped so two "
            "copies of one link dedupe to one paper.")
    example = "https://consensus.app/papers/details/cd3618ac46e15447b9a943510708dc4b/"
    patterns = (CONSENSUS_RE,)
    raw_label = "Consensus link"
    raw_placeholder = "https://consensus.app/papers/details/..."

    def canonical_url(self, ident):
        return f"https://consensus.app/papers/details/{ident['consensus']}/"
