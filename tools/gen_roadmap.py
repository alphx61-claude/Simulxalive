#!/usr/bin/env python3
"""Render ROADMAP.md and the tracking page from docs/roadmap.json.

docs/roadmap.json is the single source of truth. Both outputs are generated;
edit the JSON, never the outputs. Templates live in tools/templates.
Visual system: Dala (docs/DESIGN.md).
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pages import PALETTE, ROOT, render                           # noqa: E402
R = json.loads((ROOT / "docs" / "roadmap.json").read_text())

STATUS = {"done": PALETTE["saffron"], "next": PALETTE["iris"], "planned": PALETTE["muted"]}


def phases():
    """The phases, each carrying its own tally so the templates stay declarative."""
    out = []
    for p in R["phases"]:
        done = sum(1 for m in p["milestones"] if m["done"])
        total = len(p["milestones"])
        out.append({**p, "done": done, "total": total, "color": STATUS[p["status"]],
                    "pct": (done / total * 100) if total else 0, "exit": p.get("exit", "")})
    return out


def page(template, **extra):
    ps = phases()
    return render(
        template,
        project=R["project"], premise=R["premise"], decisions=R["decisions"],
        invariants=R["invariants"], phases=ps,
        done=sum(p["done"] for p in ps), total=sum(p["total"] for p in ps), **extra)


if __name__ == "__main__":
    (ROOT / "ROADMAP.md").write_text(page("roadmap.md.j2"))
    (ROOT / "dist").mkdir(exist_ok=True)
    (ROOT / "dist" / "roadmap.html").write_text(page("roadmap.html.j2", c=PALETTE))
    ps = phases()
    print(f"ROADMAP.md and dist/roadmap.html written - "
          f"{sum(p['done'] for p in ps)}/{sum(p['total'] for p in ps)} milestones")
