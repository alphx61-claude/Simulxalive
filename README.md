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
| `data/inbox.json` | Submitted papers waiting on review — not yet part of the corpus |

### On the scores

`convergence` and `robustness` are **our codings of the cited literature against the
rubric in `data/axes.json`** — they are not figures reported by the papers. Every
coding carries the studies it rests on and a `note` naming the caveat, so each one can
be argued with individually. `evidence` records whether a finding is replicated across
independent labs (`strong`), replicated with material caveats (`mixed`), or directly
disputed (`contested`); it weights every aggregate above.

Figures quoted inside `finding` and `note` fields **are** from the papers.

## Adding a source

Papers arrive through **input sockets** — one contract covering a DOI, an arXiv id, an
OpenAlex id, a Consensus link, a bare URL or a typed citation:

```bash
python3 tools/ingest.py sockets                 # what inputs exist
python3 tools/ingest.py submit "10.1073/pnas.2405460121" --axis prompt-invariance \
    --set title="..." --set authors="..." --set year=2024 --set venue="PNAS Nexus"
python3 tools/ingest.py queue                   # what is waiting on a person
python3 tools/ingest.py accept <key> --by <you> # the only path into sources.json
python3 tools/validate.py                       # referential integrity
```

There is a GUI for the same thing — `site/submit.html`, a single generated page with no
backend. It routes a pasted reference, tags it against the taxonomy and emits the
submission envelope; you replay that envelope through the command above. Rebuild it with
`python3 tools/gen_site.py` after touching a socket.

A submission stages in `data/inbox.json` and goes nowhere until someone accepts it.
Nothing fills in metadata on your behalf: a draft missing its title, authors, year,
venue or URL is refused at the gate rather than completed by guesswork. Each socket
declares its own fields and detection patterns, so the site's input sockets will render
from the same manifest the CLI prints — see `docs/SOCKETS.md`.

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

Design canvas, the input-socket layer that sources arrive through, and its submission
page. The atlas itself is not started; see `ROADMAP.md`.
