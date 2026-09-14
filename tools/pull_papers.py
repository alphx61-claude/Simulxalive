#!/usr/bin/env python3
"""Drive the ingestion backend from a terminal: watch a pull happen live.

    python3 -m server &                                  # start the backend
    python3 tools/pull_papers.py --list-axes
    python3 tools/pull_papers.py --axis anchoring --source crossref --limit 20

This is a client, not a second implementation: every decision - what to search
for, what counts as already known, what gets staged - belongs to the server.
"""
import argparse
import asyncio
import contextlib
import pathlib
import signal
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from server.client import Client                                    # noqa: E402

DIM, BOLD, AMBER, VIOLET, OFF = "\033[2m", "\033[1m", "\033[38;5;214m", "\033[38;5;99m", "\033[0m"


def args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--token")
    p.add_argument("--list-axes", action="store_true", help="print the axes and their queries")
    p.add_argument("--axis", help="axis id to pull for, e.g. tom-false-belief")
    p.add_argument("--query", help="free-text query instead of, or alongside, an axis")
    p.add_argument("--side", default="any", choices=("any", "human", "machine", "bridge"))
    p.add_argument("--source", default="openalex")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--per-page", type=int)
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--include-known", action="store_true")
    p.add_argument("--no-stage", action="store_true", help="stream only, write nothing")
    return p.parse_args()


async def main(a):
    client = await Client.connect(a.host, a.port, token=a.token)
    try:
        if a.list_axes:
            await client.send({"type": "corpus.axes", "params": {"side": a.side}})
            ev, _ = await client.recv_until("axes")
            for axis in ev["axes"]:
                print(f"{AMBER}{axis['id']:28s}{OFF} {axis['label']}\n{DIM}    {axis['query']}{OFF}")
            return 0
        if not (a.axis or a.query):
            print("give --axis, --query, or --list-axes", file=sys.stderr)
            return 2

        params = {"source": a.source, "limit": a.limit, "side": a.side,
                  "include_known": a.include_known, "stage": not a.no_stage}
        for key in ("axis", "query", "from_year", "to_year", "per_page"):
            value = getattr(a, key)
            if value is not None:
                params[key] = value
        await client.send({"type": "pull.start", "id": "cli", "params": params})
        return await stream(client)

    finally:
        await client.close()


async def stream(client):
    """Print the event stream until the job ends. Ctrl-C asks the server to stop."""
    job = None
    interrupts = []

    def interrupt():
        interrupts.append(1)
        if len(interrupts) > 1 or not job:
            raise KeyboardInterrupt
        print("\ncancelling; press ctrl-c again to just leave", file=sys.stderr)
        asyncio.create_task(client.send({"type": "pull.cancel", "params": {"job": job}}))

    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGINT, interrupt)
    try:
        while True:
            ev = await client.recv(timeout=120)
            kind = ev["type"]
            if kind == "ack":
                job = ev.get("job")
            elif kind == "job.started":
                print(f"{BOLD}{ev['job']}{OFF} {ev['source']}: {ev['query']}")
                print(f"{DIM}staging to {ev['staged_path'] or '(not staging)'}{OFF}")
            elif kind == "paper":
                mark = VIOLET + "new" + OFF if ev["dedup"]["status"] == "new" else \
                    DIM + ev["dedup"]["status"] + OFF
                r = ev["record"]
                cites = (r.get("citations") or {}).get("value") if isinstance(
                    r.get("citations"), dict) else None
                print(f"  {mark:>22} {r.get('year') or '????'}  {(r.get('title') or '')[:78]}"
                      + (f" {DIM}[{cites} cites]{OFF}" if cites else ""))
            elif kind == "job.progress":
                print(f"{DIM}  ... {ev['fetched']} fetched, {ev['new']} new{OFF}")
            elif kind == "job.done":
                s = ev["summary"]
                print(f"{BOLD}done{OFF} {s['new']} new of {s['fetched']} fetched "
                      f"({s['in_corpus']} already in the corpus, {s['already_staged']} staged "
                      f"before, {s['duplicate_in_run']} repeats) in {s['elapsed_s']}s")
                if ev["staged_path"]:
                    print(f"{DIM}candidates: {ev['staged_path']}{OFF}")
                return 0
            elif kind in ("job.failed", "error"):
                err = ev["error"]
                print(f"{BOLD}{err['code']}{OFF}: {err['message']}", file=sys.stderr)
                if err.get("retry_after"):
                    print(f"upstream asks for {err['retry_after']}s", file=sys.stderr)
                return 1
            elif kind == "job.cancelled":
                s = ev["summary"]
                print(f"cancelled after {s['fetched']} records; {s['new']} staged")
                return 130
    finally:
        with contextlib.suppress(NotImplementedError, ValueError):
            loop.remove_signal_handler(signal.SIGINT)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(args())))
