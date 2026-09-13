# Data model

## The reframe

v1 made **constructs** the graph nodes: 28 abstract capacities, each with a human
side and a machine side. That renders a snapshot, not a trajectory.

v2 makes **papers and paper clusters** the nodes. Papers carry dates, so the graph
gains a time axis and can show the thing the project exists to show: how the gap has
moved. The 28 constructs do not disappear — they demote to the **taxonomy** that tags
papers and carries the scores.

```
     axis  (taxonomy: 28 constructs, the rubric, the scores)
       |
       | tags
       v
    paper  ──member of──>  cluster        both render as graph nodes
       |                      |
       └──── edges ───────────┘           lineage | correspondence | contradiction

  measurement  (our own eval runs, scored on the same axes)
```

## Entities

### `paper`
One real publication. Gets its own node when `major` is true; otherwise it is
represented by its cluster.

| Field | Notes |
|---|---|
| `id` | stable slug, e.g. `kosinski2024` |
| `title`, `authors`, `year`, `venue`, `url`, `doi` | bibliographic |
| `domain` | `human` · `machine` · `bridge` — bridge papers measure both sides directly |
| `citations` | for node sizing and the `major` test |
| `axes` | which constructs it bears on |
| `cluster` | cluster id, or null for a standalone major node |
| `major` | own node, or folded into its cluster |
| `provenance` | how it entered: `seed`, `ingest`, `manual`; who accepted it |

### `cluster`
A group of papers that acts as one node — the default for anything not major.

`id`, `label`, `domain`, `axes`, `members[]`, `year_span`, `centroid_year`.

### `axis`
The existing 28 constructs, unchanged in spirit: label, family, instrument, rubric
scores, sources, the caveat note. Two additions:

- `history[]` — scores at multiple timepoints, so progress is expressible.
- `instrument_id` — links to an eval-harness instrument once Phase 4 lands.

### `edge`
| Kind | Meaning |
|---|---|
| `lineage` | within one domain; B builds on A |
| `correspondence` | across domains; a machine result addresses a human finding on a shared axis |
| `contradiction` | one paper disputes another's result |

`contradiction` matters more than it sounds. The literature genuinely disagrees with
itself — false-belief results against their trivial-alteration rebuttals, anchoring
found against anchoring absent, near-perfect correlation against near-total
disagreement on the same moral ratings. Averaging those away would be the single
easiest way to make this project dishonest. They render as a distinct edge.

### `measurement`
Produced by the eval harness, not read from a paper.

`axis_id`, `instrument_id`, `model`, `run_date`, `variant` (which perturbation),
`value`, `n`, `ci`. Measured and cited results live in the same schema so a chart can
draw both, distinguished by provenance rather than by living in different files.

## Node sizing and the `major` test

A paper earns its own node when it is load-bearing for an axis: it established the
result, or it is the standing rebuttal. Citation count informs the call but does not
make it — a highly cited paper that merely replicates belongs in its cluster, and a
lightly cited rebuttal that overturns a headline result does not.

That judgement is human, recorded in `provenance`, and reversible.

## Time

Every node has a year; every axis has a scored history. The atlas exposes this as a
scrubber: drag to a year, and the corpus, the edges and the convergence figure all
resolve to what was known then. Thin evidence must look thin — early years show wide
uncertainty rather than a confident line.

## Migration from v1

`data/axes.json` and `data/protocols.json` survive as-is. `data/sources.json` becomes
the seed for `data/papers.json`: each of the 61 entries gains `domain`, `citations`,
`axes` and `provenance: seed`. Nothing is thrown away.
