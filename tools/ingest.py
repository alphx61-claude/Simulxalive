#!/usr/bin/env python3
"""Submit and review paper sources through the socket layer.

    tools/ingest.py sockets                      # what inputs exist
    tools/ingest.py submit "10.1073/pnas.2405460121" --axis prompt-invariance \
        --set title="..." --set authors="..." --set year=2024 --set venue="PNAS"
    tools/ingest.py queue                        # what is waiting on a person
    tools/ingest.py accept doi:10.1073/pnas.2405460121 --by taran
    tools/ingest.py reject arxiv:2303.11436 --reason "superseded by the journal version"

The same envelope this CLI builds is what the site's input sockets will post -
see docs/SOCKETS.md. `submit --json -` reads that envelope from stdin, so the
web path and this path exercise identical code.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import sockets                                                    # noqa: E402
from sockets import SocketError, store                            # noqa: E402

BULLET = "  - "


def out(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    return obj


# ------------------------------------------------------------------- sockets
def cmd_sockets(a):
    manifest = sockets.manifest()
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {a.out}")
        return 0
    if a.json:
        return out(manifest, True) and 0
    for s in manifest["sockets"]:
        req = [f["name"] for f in s["fields"] if f["required"]]
        print(f"{s['name']:<10} {s['label']}")
        print(f"{BULLET}{s['help']}")
        print(f"{BULLET}required: {', '.join(req) or 'none'}")
        print(f"{BULLET}e.g. {s['example']}")
    print(f"\nasked on every socket: {', '.join(f['name'] for f in manifest['common'])}")
    return 0


# -------------------------------------------------------------------- submit
def cmd_submit(a):
    if a.json:
        text = sys.stdin.read() if a.json == "-" else a.json
        payload = json.loads(text)
    else:
        values = {}
        for pair in a.set:
            if "=" not in pair:
                print(f"--set expects key=value, got {pair!r}", file=sys.stderr)
                return 2
            k, v = pair.split("=", 1)
            values[k.strip()] = v
        if a.raw:
            values["raw"] = a.raw
        payload = {"socket": a.socket, "values": values, "axes": a.axis,
                   "domain": a.domain, "note": a.note, "submitted_by": a.by}

    result = sockets.submit(payload, allow_duplicate=a.allow_duplicate)
    if a.as_json:
        return out(result, True) and 0
    d = result["draft"]
    print(f"staged {result['key']}  (socket: {result['socket']})")
    print(f"{BULLET}" + (d["title"] or "title unknown"))
    for w in result["warnings"]:
        print(f"{BULLET}{w}")
    print(f"\nreview with: tools/ingest.py accept {result['key']} --by <you>")
    return 0


# --------------------------------------------------------------------- queue
def cmd_queue(a):
    rows = sockets.queue(None if a.all else "pending")
    if a.as_json:
        return out(rows, True) and 0
    if not rows:
        print("inbox empty")
        return 0
    for r in rows:
        flag = "" if not r.get("warnings") else f"  ({len(r['warnings'])} warning(s))"
        print(f"[{r['status']:<8}] {r['key']}{flag}")
        print(f"{BULLET}{r.get('title') or 'title unknown'}"
              f"{'  ' + str(r['year']) if r.get('year') else ''}")
        if r.get("axes"):
            print(f"{BULLET}axes: {', '.join(r['axes'])}")
        if r.get("source_id"):
            print(f"{BULLET}accepted as {r['source_id']}")
    return 0


def cmd_show(a):
    row = store.find(a.key)
    if row is None:
        print(f"no submission with key '{a.key}'", file=sys.stderr)
        return 1
    return out(row, True) and 0


# -------------------------------------------------------------- review gate
def cmd_accept(a):
    result = sockets.accept(a.key, by=a.by, source_id=a.id)
    if a.as_json:
        return out(result, True) and 0
    print(f"accepted {a.key} into data/sources.json as {result['source_id']}")
    print(f"{BULLET}run tools/validate.py before committing")
    return 0


def cmd_reject(a):
    sockets.reject(a.key, reason=a.reason, by=a.by)
    print(f"rejected {a.key}: {a.reason}")
    return 0


# ----------------------------------------------------------------------- cli
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sockets", help="list the available inputs")
    s.add_argument("--json", action="store_true", help="emit the full manifest")
    s.add_argument("--out", help="write the manifest to a file for the site to ship")
    s.set_defaults(fn=cmd_sockets)

    s = sub.add_parser("submit", help="stage a paper source for review")
    s.add_argument("raw", nargs="?", help="the reference, pasted whole")
    s.add_argument("--socket", help="force a socket instead of auto-routing")
    s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="a socket field, repeatable")
    s.add_argument("--axis", action="append", default=[], help="axis id, repeatable")
    s.add_argument("--domain", help="human | machine | bridge")
    s.add_argument("--note", default="")
    s.add_argument("--by", default="", help="who is submitting")
    s.add_argument("--json", help="a whole submission envelope, or - for stdin")
    s.add_argument("--allow-duplicate", action="store_true")
    s.add_argument("--as-json", action="store_true", help="print the result as JSON")
    s.set_defaults(fn=cmd_submit)

    s = sub.add_parser("queue", help="what is waiting on review")
    s.add_argument("--all", action="store_true", help="include accepted and rejected")
    s.add_argument("--as-json", action="store_true")
    s.set_defaults(fn=cmd_queue)

    s = sub.add_parser("show", help="print one submission")
    s.add_argument("key")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("accept", help="move a draft into the bibliography")
    s.add_argument("key")
    s.add_argument("--by", required=True, help="who is vouching for it")
    s.add_argument("--id", help="override the generated source id")
    s.add_argument("--as-json", action="store_true")
    s.set_defaults(fn=cmd_accept)

    s = sub.add_parser("reject", help="close a draft without adding it")
    s.add_argument("key")
    s.add_argument("--reason", required=True)
    s.add_argument("--by", default="")
    s.set_defaults(fn=cmd_reject)

    a = p.parse_args(argv)
    try:
        return a.fn(a) or 0
    except SocketError as e:
        print(f"refused [{e.code}]: {e.message}", file=sys.stderr)
        for k, v in e.extra.items():
            print(f"{BULLET}{k}: {v}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
