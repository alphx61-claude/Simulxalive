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
| `docs/roadmap.json` | phases and milestones — **the state of the project** |
| `docs/DATA-MODEL.md` | v2 schema: papers and clusters as nodes |
| `docs/DESIGN.md` | the visual system |
| `docs/BACKEND.md` | the ingestion backend: protocol, record shape, staging |
| `server/` | WebSocket backend that pulls papers into `data/ingest/` |
| `tests/` | `python3 -m unittest discover -s tests -t .` — no network |
| `tools/gen_artboards.py` | redraws the design plates from `data/` |
| `tools/pull_papers.py` | terminal client for the backend |
| `tools/gen_roadmap.py` | renders `ROADMAP.md` and the tracking page |
| `*.dc.html`, `canvas.json` | design canvas artboards |

## Working conventions

- Plate geometry is **computed from `data/`**. Change a score, re-run
  `python3 tools/gen_artboards.py`, and the plates redraw. Never hand-edit a generated
  artboard except `Main.dc.html`, which is authored.
- The seeded canvas (`simulxalive-atlas.html`, ~2.5 MB) is gitignored and rebuilt by
  `tools/seed.sh`.
- Validate data before committing: referential integrity between `axes`, `protocols`
  and `sources` is checked by the validator once Phase 1 lands.
- Research lookups: the Consensus MCP server returns real papers with resolvable URLs.
  Prefer it over recalling citations from memory — memory produces plausible-looking
  fabrications here.

## Status

Phase 0 complete: taxonomy, seed bibliography, paired protocols, design system and a
six-plate layout. Phase 1 (papers as graph nodes) is next; the phase-2 ingestion
backend exists ahead of it under `server/`. Nothing it pulls reaches `data/` without
a human accepting it — see `docs/BACKEND.md`. There is still no atlas application.
