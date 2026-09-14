# Input sockets

How a paper gets into the corpus. One contract, several inputs, one review gate.

A **socket** turns one kind of raw reference — a DOI, an arXiv id, a Consensus link,
a hand-typed citation — into a normalised draft. Sockets never write to
`data/sources.json`. They write to `data/inbox.json`, and a person moves a draft
across. That is the human review gate the project decided on, expressed as code:
the `accept` step is the only path into the bibliography, and it refuses anything
incomplete.

This layer exists so the site's input fields are a thin skin over it later. It ships
now with no UI and no network, because the contract is the part worth getting right
first.

## The shape

```
   raw reference
        |
        v
   route()  ──>  socket.build()  ──>  draft ──> data/inbox.json   (pending)
                      |                              |
                 resolve()                        accept()  <── a person
                 (Phase 2)                            |
                                                      v
                                              data/sources.json
```

## Sockets

| Socket | Takes | Key |
|---|---|---|
| `doi` | a DOI, bare or as a `doi.org` link | `doi:10.1073/pnas.2405460121` |
| `arxiv` | an arXiv id or `abs`/`pdf` link; versions stripped | `arxiv:2410.05229` |
| `openalex` | an OpenAlex work id — what the Phase 2 adapter speaks | `openalex:W2741809807` |
| `consensus` | a `consensus.app` paper link — how all 61 seeds arrived | `consensus:cd3618…` |
| `link` | any other paper URL; low routing weight, so a stronger id always wins | `url:https://…` |
| `manual` | a typed citation, for anything with no resolvable id | `title:…` |

`python3 tools/ingest.py sockets` prints this list live, and is the thing to trust —
the table above is prose.

## The submission envelope

The one shape everything speaks: the CLI builds it, and the site's input sockets will
post it.

```json
{
  "socket": "consensus",
  "values": { "raw": "https://consensus.app/papers/details/cd3618…/" },
  "axes": ["prompt-invariance"],
  "domain": "machine",
  "note": "Why this belongs, in words.",
  "submitted_by": "taran"
}
```

- `socket` is optional. Omit it and `values.raw` is routed by pattern.
- `values` carries that socket's declared fields. Any of `title`, `authors`, `year`,
  `venue`, `url` may be supplied by hand, and hand-typed values win over a resolver.
- `axes` are construct ids from `data/axes.json`; an unknown one is refused, not
  silently dropped.
- `domain` is `human`, `machine` or `bridge` (`docs/DATA-MODEL.md`).

`submit()` returns `{ok, status, key, draft, missing, warnings}` or raises a
`SocketError` carrying a stable `code`: `unroutable`, `unknown_socket`,
`parse_failed`, `field_missing`, `bad_field`, `unknown_axis`, `bad_domain`,
`duplicate`, `incomplete`, `not_found`, `not_pending`, `id_taken`.

## Rendering the inputs from the registry

Each socket declares its own fields and its own detection patterns, so the form is
data, not markup. Ship the manifest beside the page — Phase 3 is a static site, so
there is no backend to ask:

```bash
python3 tools/ingest.py sockets --out dist/sockets.json
```

```json
{
  "common": [ { "name": "axes", "label": "Axes", "kind": "multiselect", … } ],
  "domains": ["human", "machine", "bridge"],
  "citation_fields": ["title", "authors", "year", "venue", "url"],
  "sockets": [
    { "name": "doi", "label": "DOI", "help": "…", "example": "…",
      "patterns": ["10\\.\\d{4,9}/[^\\s\"'<>,;]+"], "weight": 1.0,
      "fields": [ { "name": "raw", "label": "DOI", "kind": "text", "required": true } ] }
  ]
}
```

`patterns` are deliberately ECMAScript-safe — no named groups, no lookbehind — so the
browser routes a paste exactly as Python does, from the same strings. Highest
`weight` among matching sockets wins; `manual` never auto-routes.

Since the site is static, a browser submission cannot write `data/inbox.json` itself.
It builds the envelope above and hands it off — a downloaded `.json`, a prefilled
issue, a clipboard copy — and the envelope is replayed through the same code:

```bash
python3 tools/ingest.py submit --json - < submission.json
```

## Adding or changing a socket

Copy `tools/sockets/doi.py`, change the class attributes, import it in
`tools/sockets/__init__.py`. Routing, the manifest, the CLI and the form pick it up
with no other edit.

```python
@register
class PubmedSocket(ReferenceSocket):
    name, kind, label = "pubmed", "pubmed", "PubMed"
    help = "A PMID or a pubmed.ncbi.nlm.nih.gov link."
    example = "PMID: 38200290"
    patterns = (r"pubmed\.ncbi\.nlm\.nih\.gov/\d{6,9}", r"pmid:?\s*\d{6,9}")

    def canonical_url(self, ident):
        return f"https://pubmed.ncbi.nlm.nih.gov/{ident['pubmed']}/"
```

A new identifier kind also needs a parser in `tools/sockets/identifiers.py` and an
entry in `sniff()` and `key_for()` — that is the whole list. Then run
`python3 tools/test_sockets.py`.

## What this layer will not do

- **It will not invent metadata.** With no resolver installed, a bare DOI produces a
  draft whose title, authors, year and venue are `null` and which `accept` refuses.
  Someone types them, or the paper does not enter. This is ground rule 1 as code.
- **It does not fetch.** Filling a draft from an identifier is a network job and
  belongs to the Phase 2 OpenAlex adapter, which installs itself at the seam in
  `tools/sockets/resolve.py` via `resolve.use(...)`. Nothing else changes when it
  lands.
- **It does not score.** `convergence` and `robustness` are codings argued by a
  person against the rubric. No socket writes them.
- **It does not merge across identifiers.** The same paper submitted once by DOI and
  once by Consensus link produces two keys, and a reviewer catches it. A resolver
  makes this automatic; until then the gate is the answer, not a guess.

## Commands

```bash
python3 tools/ingest.py sockets                 # what inputs exist
python3 tools/ingest.py submit "<reference>" --axis <id> --domain <d> --by <you>
python3 tools/ingest.py queue                   # what is waiting on a person
python3 tools/ingest.py show <key>
python3 tools/ingest.py accept <key> --by <you> # the gate: writes sources.json
python3 tools/ingest.py reject <key> --reason "…"
python3 tools/validate.py                       # referential integrity, run before committing
python3 tools/test_sockets.py                   # self-test, run after touching a socket
```
