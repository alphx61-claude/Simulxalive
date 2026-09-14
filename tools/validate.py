#!/usr/bin/env python3
"""Check the data files hold together. Run before committing anything under data/.

    python3 tools/validate.py          # errors fail with exit 1, warnings do not

Referential integrity between axes, protocols, sources and the socket inbox:
every cited id resolves, every inbox row points somewhere real, nothing is
staged twice. It does not judge a coding - that is a human argument, not a
check - but it does catch a score that fell outside the rubric's range.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ERRORS, WARNINGS = [], []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def load(name):
    path = DATA / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        err(f"{name}: not valid JSON - {e}")
        return None


def main():
    axes_doc = load("axes.json") or {"axes": []}
    protocols = load("protocols.json") or {"protocols": []}
    sources_doc = load("sources.json") or {"sources": {}}
    inbox = load("inbox.json") or {"submissions": []}

    sources = sources_doc.get("sources", {})
    axes = axes_doc.get("axes", [])
    axis_ids = {a["id"] for a in axes}
    cited = set()

    # ------------------------------------------------------------ bibliography
    seen_urls = {}
    for sid, s in sources.items():
        for f in ("authors", "year", "title", "venue", "url"):
            if not s.get(f):
                err(f"sources.{sid}: missing '{f}'")
        url = (s.get("url") or "").split("?")[0].rstrip("/")
        if url and url in seen_urls:
            err(f"sources.{sid}: same url as sources.{seen_urls[url]}")
        seen_urls[url] = sid

    # -------------------------------------------------------------------- axes
    for a in axes:
        for ref in a.get("sources", []):
            cited.add(ref)
            if ref not in sources:
                err(f"axes.{a['id']}: cites unknown source '{ref}'")
        for score in ("convergence", "robustness"):
            v = a.get(score)
            if not isinstance(v, (int, float)) or not 0 <= v <= 1:
                err(f"axes.{a['id']}: {score} must be 0-1, got {v!r}")
        if not a.get("sources"):
            err(f"axes.{a['id']}: no sources - a coding with nothing behind it")

    # --------------------------------------------------------------- protocols
    for p in protocols.get("protocols", []):
        ref = p.get("source")
        cited.add(ref)
        if ref not in sources:
            err(f"protocols.{p.get('id')}: cites unknown source '{ref}'")

    for sid in sources:
        if sid not in cited:
            warn(f"sources.{sid}: cited by no axis or protocol")

    # ------------------------------------------------------------------- inbox
    keys, valid = set(), {"pending", "accepted", "rejected"}
    for row in inbox.get("submissions", []):
        key = row.get("key")
        if not key:
            err("inbox: a submission with no key")
            continue
        if key in keys:
            err(f"inbox.{key}: staged twice")
        keys.add(key)
        if row.get("status") not in valid:
            err(f"inbox.{key}: status {row.get('status')!r} is not one of {sorted(valid)}")
        for ax in row.get("axes", []):
            if ax not in axis_ids:
                err(f"inbox.{key}: unknown axis '{ax}'")
        if row.get("status") == "accepted":
            sid = row.get("source_id")
            if sid not in sources:
                err(f"inbox.{key}: accepted as '{sid}', which is not in sources.json")
        elif row.get("status") == "pending":
            warn(f"inbox.{key}: pending review")

    # ------------------------------------------------------------------ report
    for w in WARNINGS:
        print(f"warn   {w}")
    for e in ERRORS:
        print(f"ERROR  {e}")
    print(f"\n{len(axes)} axes, {len(protocols.get('protocols', []))} protocols, "
          f"{len(sources)} sources, {len(inbox.get('submissions', []))} submissions")
    print(f"{len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
