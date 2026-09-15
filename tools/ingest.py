#!/usr/bin/env python3
"""Submit and review paper sources through the socket layer.

    tools/ingest.py sockets                      # what inputs exist
    tools/ingest.py submit "10.1073/pnas.2405460121" --axis prompt-invariance \
        --set title="..." --set authors="..." --set year=2024 --set venue="PNAS"
    tools/ingest.py queue                        # what is waiting on a person
    tools/ingest.py accept doi:10.1073/pnas.2405460121 --by taran
    tools/ingest.py reject arxiv:2303.11436 --reason "superseded by the journal version"

The same envelope this CLI builds is what site/submit.html emits - see
docs/SOCKETS.md. `submit --json -` reads that envelope from stdin, so the web
path and this path exercise identical code.
"""
import json
import pathlib
import sys

import click

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import sockets                                                    # noqa: E402
from sockets import SocketError, store                            # noqa: E402

BULLET = "  - "


def emit(obj):
    click.echo(json.dumps(obj, indent=2, ensure_ascii=False))


class Layer(click.Group):
    """A refusal from the layer is a message and exit 1, not a traceback."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except SocketError as e:
            click.echo(f"refused [{e.code}]: {e.message}", err=True)
            for k, v in e.extra.items():
                click.echo(f"{BULLET}{k}: {v}", err=True)
            ctx.exit(1)


@click.group(cls=Layer, help=__doc__.split("\n")[0],
             context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    pass


@cli.command("sockets", help="list the available inputs")
@click.option("--json", "as_json", is_flag=True, help="emit the full manifest")
@click.option("--out", type=click.Path(), help="write the manifest to a file for the site to ship")
def list_sockets(as_json, out):
    manifest = sockets.manifest()
    if out:
        pathlib.Path(out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        return click.echo(f"wrote {out}")
    if as_json:
        return emit(manifest)
    for s in manifest["sockets"]:
        required = [f["name"] for f in s["fields"] if f["required"]]
        click.echo(f"{s['name']:<10} {s['label']}")
        click.echo(f"{BULLET}{s['help']}")
        click.echo(f"{BULLET}required: {', '.join(required) or 'none'}")
        click.echo(f"{BULLET}e.g. {s['example']}")
    click.echo(f"\nasked on every socket: {', '.join(f['name'] for f in manifest['common'])}")


@cli.command(help="stage a paper source for review")
@click.argument("raw", required=False)
@click.option("--socket", help="force a socket instead of auto-routing")
@click.option("--set", "fields", multiple=True, metavar="KEY=VALUE",
              help="a socket field, repeatable")
@click.option("--axis", "axes", multiple=True, help="axis id, repeatable")
@click.option("--domain", help="human | machine | bridge")
@click.option("--note", default="")
@click.option("--by", default="", help="who is submitting")
@click.option("--json", "envelope", help="a whole submission envelope, or - for stdin")
@click.option("--allow-duplicate", is_flag=True)
@click.option("--as-json", is_flag=True, help="print the result as JSON")
def submit(raw, socket, fields, axes, domain, note, by, envelope, allow_duplicate, as_json):
    if envelope:
        payload = json.loads(sys.stdin.read() if envelope == "-" else envelope)
    else:
        if any("=" not in pair for pair in fields):
            raise click.BadParameter("expected KEY=VALUE", param_hint="--set")
        values = {k.strip(): v for k, v in (p.split("=", 1) for p in fields)}
        if raw:
            values["raw"] = raw
        payload = {"socket": socket, "values": values, "axes": list(axes),
                   "domain": domain, "note": note, "submitted_by": by}

    result = sockets.submit(payload, allow_duplicate=allow_duplicate)
    if as_json:
        return emit(result)
    click.echo(f"staged {result['key']}  (socket: {result['socket']})")
    click.echo(BULLET + (result["draft"]["title"] or "title unknown"))
    for w in result["warnings"]:
        click.echo(f"{BULLET}{w}")
    click.echo(f"\nreview with: tools/ingest.py accept {result['key']} --by <you>")


@cli.command(help="what is waiting on review")
@click.option("--all", "everything", is_flag=True, help="include accepted and rejected")
@click.option("--as-json", is_flag=True)
def queue(everything, as_json):
    rows = sockets.queue(None if everything else "pending")
    if as_json:
        return emit(rows)
    if not rows:
        return click.echo("inbox empty")
    for r in rows:
        warnings = f"  ({len(r['warnings'])} warning(s))" if r.get("warnings") else ""
        year = f"  {r['year']}" if r.get("year") else ""
        click.echo(f"[{r['status']:<8}] {r['key']}{warnings}")
        click.echo(f"{BULLET}{r.get('title') or 'title unknown'}{year}")
        if r.get("axes"):
            click.echo(f"{BULLET}axes: {', '.join(r['axes'])}")
        if r.get("source_id"):
            click.echo(f"{BULLET}accepted as {r['source_id']}")


@cli.command(help="print one submission")
@click.argument("key")
def show(key):
    row = store.find(key)
    if row is None:
        raise SocketError("not_found", f"No submission with key '{key}'.")
    emit(row)


@cli.command(help="move a draft into the bibliography")
@click.argument("key")
@click.option("--by", required=True, help="who is vouching for it")
@click.option("--id", "source_id", help="override the generated source id")
@click.option("--as-json", is_flag=True)
def accept(key, by, source_id, as_json):
    result = sockets.accept(key, by=by, source_id=source_id)
    if as_json:
        return emit(result)
    click.echo(f"accepted {key} into data/sources.json as {result['source_id']}")
    click.echo(f"{BULLET}run tools/validate.py before committing")


@cli.command(help="close a draft without adding it")
@click.argument("key")
@click.option("--reason", required=True)
@click.option("--by", default="")
def reject(key, reason, by):
    sockets.reject(key, reason=reason, by=by)
    click.echo(f"rejected {key}: {reason}")


if __name__ == "__main__":
    cli()
