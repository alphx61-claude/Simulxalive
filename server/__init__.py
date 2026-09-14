"""Simulxalive ingestion backend: pull papers from bibliographic APIs over WebSocket.

Phase 2 of the roadmap (docs/roadmap.json) grows the corpus semi-automatically
behind a human review gate. This package is the machine half of that: a client
opens a WebSocket, asks for papers on an axis, and receives candidate records as
they arrive. Nothing here writes to data/sources.json - pulled records land in
data/ingest/ marked unreviewed, and a human decides what becomes a paper node.

Stdlib only, like everything else in this repository.
"""

__version__ = "0.1.0"
