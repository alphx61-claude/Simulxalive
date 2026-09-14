# Simulxalive

An atlas of where human and machine cognition actually diverge.

Twenty-eight constructs are measured on **both** sides using the same instruments,
drawn from published human-subject research and published model evaluations. Each
pairing is scored on two axes that are usually conflated:

- **Convergence** — how closely the model's result matches the human result.
- **Robustness** — whether that match survives trivial, meaning-preserving
  perturbation of the task: renaming entities, reordering options, reformatting
  labels, dropping a persona prompt.

Separating them is the point of the project. On current evidence the constructs
with the *highest* convergence tend to have the *lowest* robustness — the three-party
Turing test sits at 0.95 convergence and 0.30 robustness; false-belief attribution at
0.85 and 0.25. A picture that plots only convergence gets the story backwards.

## Current readings

| Index | Value | Over |
|---|---|---|
| Behavioural indistinguishability | **0.65** | 22 behavioural constructs, evidence-weighted |
| Fragility of that match | **0.49** | share that fails under trivial rewording |
| Neural alignment | **0.69** | 3 representational-alignment constructs |
| Substrate divergence | **0.94** | data to fluency, power budget, prompt invariance |

The headline reading: behaviour converges, internal representations converge, and the
machine underneath does not converge at all. That supports **substrate-independence of
measurable behaviour**. It is not evidence for the simulation hypothesis, and the atlas
says so explicitly — see `Verdict.dc.html` and the sources under "Simulation argument"
in `data/sources.json`.

## Data

| File | What it holds |
|---|---|
| `data/axes.json` | The 28 paired constructs, scores, rubric, family grouping |
| `data/protocols.json` | 7 protocols where humans **and** models both report a number on one scale |
| `data/sources.json` | 61 papers, cited by id from the other two files |

### On the scores

`convergence` and `robustness` are **our codings of the cited literature against the
rubric in `data/axes.json`** — they are not figures reported by the papers. Every
coding carries the studies it rests on and a `note` naming the caveat, so each one can
be argued with individually. `evidence` records whether a finding is replicated across
independent labs (`strong`), replicated with material caveats (`mixed`), or directly
disputed (`contested`); it weights every aggregate above.

Figures quoted inside `finding` and `note` fields **are** from the papers.

## Pulling papers

The corpus grows through a WebSocket backend that searches bibliographic APIs per
axis, drops what we already have, and streams the rest as candidates for review:

```bash
python3 -m server --contact you@example.org            # ws://127.0.0.1:8787/ws
python3 tools/pull_papers.py --axis tom-false-belief --side machine --limit 20
```

Nothing it pulls enters the corpus on its own. Candidates land in `data/ingest/`
with `review.status: pending`, their citation counts carrying the date and the
upstream field they came from, and every judgement the rubric calls for left null
for a person to make. Protocol and record shape: `docs/BACKEND.md`.

## Design canvas

The visual design lives as artboards in the repository root (`*.dc.html`) plus
`canvas.json`. The published canvas is regenerated, not hand-edited:

```bash
python3 tools/gen_artboards.py          # redraw plates from data/
SKILL_DIR=<design skill dir> tools/seed.sh   # rebuild the full canvas
```

`tools/gen_artboards.py` computes every mark position from `data/`, so changing a score
changes the plates. `Main.dc.html` is hand-authored (the hero constellation).

Visual system: **Dala** — see `docs/DESIGN.md`.

## Status

Design canvas, plus the ingestion backend (roadmap phase 2) that pulls candidate
papers over a WebSocket. The atlas itself is not started.
