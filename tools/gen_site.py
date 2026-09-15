#!/usr/bin/env python3
"""Render site/submit.html from the socket registry and the taxonomy.

The page is generated, like ROADMAP.md and the plates: every input, every
detection pattern and every axis id comes from `tools/sockets` and `data/` at
build time, so the form cannot drift from the layer behind it. Edit a socket,
re-run this, commit the result. Never hand-edit the output.

    python3 tools/gen_site.py

The template is tools/templates/submit.html.j2. Runtime data rides in a JSON
island rather than being substituted into the script body, so the page's
JavaScript is static text - nothing to escape, nothing to interpolate.

Visual system: Dala (docs/DESIGN.md). Contract: docs/SOCKETS.md.
"""
import json
import pathlib
import sys

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import sockets                                        # noqa: E402
from sockets import identifiers as ident              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "submit.html"

PALETTE = {"void": "#000000", "bone": "#ffffff", "ash": "#9a9a9a", "silver": "#bdbdbd",
           "iris": "#8052ff", "saffron": "#ffb829", "muted": "#6a6a6a", "hair": "#1c1c1c"}


def load(name):
    return json.loads((ROOT / "data" / name).read_text())


def bootstrap():
    """Everything the page needs at runtime, resolved at build time."""
    axes_doc = load("axes.json")
    families = axes_doc["families"]
    axes = sorted(({"id": a["id"], "label": a["label"], "family": a["family"]}
                   for a in axes_doc["axes"]),
                  key=lambda a: (families[a["family"]]["order"], a["label"]))
    return {
        "manifest": sockets.manifest(),
        "axes": axes,
        "families": {k: v["label"] for k, v in families.items()},
        # The extraction patterns, lifted straight off identifiers.py so the
        # browser and Python read a reference the same way.
        "ident": {"doi": ident.DOI_RE, "arxivNew": ident.ARXIV_NEW_RE,
                  "arxivOld": ident.ARXIV_OLD_RE, "openalex": ident.OPENALEX_RE,
                  "consensus": ident.CONSENSUS_RE, "url": ident.URL_RE},
        "sourceCount": len(load("sources.json")["sources"]),
    }


def page():
    env = Environment(loader=FileSystemLoader(ROOT / "tools" / "templates"),
                      autoescape=select_autoescape(["html", "j2"]),
                      undefined=StrictUndefined, keep_trailing_newline=True)
    data = bootstrap()
    return env.get_template("submit.html.j2").render(
        c=PALETTE, data=data, source_count=data["sourceCount"],
        examples=[s["example"] for s in data["manifest"]["sockets"][:3]])


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page())
    data = bootstrap()
    print(f"site/submit.html written - {len(data['manifest']['sockets'])} sockets, "
          f"{len(data['axes'])} axes")
