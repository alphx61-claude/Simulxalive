# Simulxalive

An atlas of how the gap between human and machine cognition has moved over time,
rendered as a graph of the research itself.

**Read `docs/roadmap.json` first** — it is the source of truth for what is done and
what is next. `ROADMAP.md` is generated from it; do not edit the generated file.

## Ground rules

These are not style preferences. Breaking them makes the project worthless.

1. **Never invent a number.** Every figure traces to a cited paper or to a measurement
   row produced by our own harness. If a paper's abstract does not give you a number
   you can quote, do not manufacture one — represent the finding qualitatively or
   leave the row out.
2. **Codings are not findings.** `convergence` and `robustness` in `data/axes.json`
   are our judgements against the rubric in that file, not figures reported by the
   papers. Label them that way in every surface that shows them.
3. **Contradictions stay visible.** Where the literature disputes itself, show the
   dispute. Never average two conflicting results into one comfortable number.
4. **Robustness outranks convergence.** The project's central finding is that the
   closest matches are the most fragile. A design or metric that hides this is wrong.
5. **The design system is settled.** Dala, specified in `docs/DESIGN.md`. Amber is
   human, violet is machine, the surface is pure black. Do not redesign it.

## Layout

| Path | What |
|---|---|
| `data/axes.json` | 28 constructs, the rubric, convergence/robustness scores |
| `data/protocols.json` | paired runs where humans and models both report a number |
| `data/sources.json` | bibliography, referenced by id from the other two |
| `data/inbox.json` | submissions staged by a socket, waiting on a person |
| `docs/roadmap.json` | phases and milestones — **the state of the project** |
| `docs/DATA-MODEL.md` | v2 schema: papers and clusters as nodes |
| `docs/DESIGN.md` | the visual system |
| `docs/SOCKETS.md` | the input-socket contract and submission envelope |
| `tools/sockets/` | one socket per way a paper can arrive; `submit()` is the layer |
| `tools/ingest.py` | submit a source, review the queue, accept into the bibliography |
| `tools/validate.py` | referential integrity across axes, protocols, sources, inbox |
| `site/submit.html` | the submission GUI — **generated** by `tools/gen_site.py` |
| `tools/gen_artboards.py` | redraws the design plates from `data/` |
| `tools/gen_roadmap.py` | renders `ROADMAP.md` and the tracking page |
| `*.dc.html`, `canvas.json` | design canvas artboards |

## Working conventions

- Plate geometry is **computed from `data/`**. Change a score, re-run
  `python3 tools/gen_artboards.py`, and the plates redraw. Never hand-edit a generated
  artboard except `Main.dc.html`, which is authored.
- The seeded canvas (`simulxalive-atlas.html`, ~2.5 MB) is gitignored and rebuilt by
  `tools/seed.sh`.
- New sources enter through a socket — `python3 tools/ingest.py submit "<reference>"` —
  rather than by hand-editing `data/sources.json`. Submissions stage in `data/inbox.json`
  and only a person moves them across (`ingest.py accept`), which records provenance and
  refuses an entry missing a field. `docs/SOCKETS.md` is the contract.
- `site/submit.html` is generated from the socket registry, like `ROADMAP.md` and the
  plates. Touch a socket or the taxonomy, re-run `python3 tools/gen_site.py`, commit the
  output. Never hand-edit it — the form's inputs, routing patterns and axis list all come
  from `tools/sockets` and `data/` at build time, which is what keeps them in step.
- Validate before committing anything under `data/`: `python3 tools/validate.py` checks
  referential integrity between `axes`, `protocols`, `sources` and the inbox. After
  touching a socket, `python3 tools/test_sockets.py`.
- Research lookups: the Consensus MCP server returns real papers with resolvable URLs.
  Prefer it over recalling citations from memory — memory produces plausible-looking
  fabrications here.

## Status

Phase 0 complete: taxonomy, seed bibliography, paired protocols, design system and a
six-plate layout. Phase 1 (papers as graph nodes) is next. The input-socket layer landed
early out of Phase 2, because the ingestion seam had to exist before the corpus grows, and
`site/submit.html` is its GUI — one static page, no backend, no network. The atlas itself
is still unbuilt, which is deliberate, not an oversight.
