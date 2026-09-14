# Simulxalive — roadmap

<!-- Generated from docs/roadmap.json by tools/gen_roadmap.py. Do not edit. -->

Show how the gap between human and machine cognition has moved over time, as a graph of the research itself.

**5 of 32 milestones complete.**

## Decisions taken

- **End product** — A progress view. Nodes are paper clusters, or individual papers where the paper is major.
- **Own evaluations** — Yes. An eval harness re-runs instruments on current models so convergence is measured, not only cited.
- **Corpus growth** — Semi-automated ingestion with a human review gate.
- **Simulation framing** — Closing argument, not the spine.

## Phases

### 0. Foundations — _done_  (4/4)

A defensible taxonomy and a settled visual language to build against.

- [x] 28-construct taxonomy with an explicit convergence/robustness rubric
- [x] 61-source seed bibliography, every entry real and linkable
- [x] 7 paired protocols where humans and models both report a number
- [x] Dala design system applied across six plates

### 1. Data model v2 - papers as nodes — _next_  (0/5)

The graph renders from real papers with real dates, so a time axis becomes possible.

- [ ] Schema for paper, cluster, edge and measurement records
- [ ] Migrate the 61 sources into paper records: year, domain, citations, axis tags
- [ ] Demote the 28 constructs from nodes to taxonomy that tags and scores papers
- [ ] Three edge kinds: lineage, correspondence, contradiction
- [ ] Referential-integrity validator wired into a pre-commit check

**Done when:** Every source is a node with a year, and the validator passes clean.

### 2. Ingestion pipeline — _planned_  (1/5)

Grow the corpus without hand-typing every record, and without letting quality slip.

- [ ] OpenAlex adapter for metadata, citations and reference edges
- [x] Discovery queries per axis, deduplicated against the existing corpus
- [ ] Review CLI: accept, reject, tag an axis, mark major, assign a cluster
- [ ] Cluster proposals from the citation graph, confirmed by hand
- [ ] Provenance on every record: how it entered and who accepted it

**Done when:** 300-500 papers in the corpus, resolving to roughly 60-80 visible nodes.

### 3. The atlas — _planned_  (0/6)

The thing people actually open.

- [ ] Static site, no backend: data ships as JSON beside the page
- [ ] Force graph, two constellations, correspondence and contradiction edges
- [ ] Time scrubber: drag a year, watch the corpus and the gap move
- [ ] Cluster nodes expand to their member papers
- [ ] Per-node panel with findings and sources
- [ ] The six plates as the scrolling argument around the graph

**Done when:** Deployed, readable on a phone, and the time scrubber tells the story without narration.

### 4. Eval harness — _planned_  (0/5)

Stop being downstream of other people's methods.

- [ ] Instruments as data: prompt templates, scoring, and perturbation variants
- [ ] Runner that records measurement rows against named models and dates
- [ ] Perturbation suite as a first-class citizen, so robustness is measured not coded
- [ ] Measured results sit beside cited ones in the same schema
- [ ] Re-run on a schedule as new models ship

**Done when:** At least eight axes carry a measured convergence and robustness number we produced ourselves.

### 5. Progress over time — _planned_  (0/4)

The headline the project exists to show.

- [ ] Axis scores as time series, combining cited history and our own runs
- [ ] Convergence and robustness plotted against year
- [ ] Comparison across model generations on identical instruments
- [ ] Honest uncertainty bands - thin evidence must look thin

**Done when:** One chart answers 'is the gap closing, and in what' without a caption.

### 6. The argument — _planned_  (0/3)

Land the reading, with the evidence behind it.

- [ ] Closing argument rewritten against the time-series evidence
- [ ] Method write-up: rubric, coding procedure, known weaknesses
- [ ] Public launch

**Done when:** A reader who disagrees can find exactly which coding to attack.

## Invariants

Breaking these makes the project worthless, not merely untidy.

1. Never invent a number. Every figure traces to a cited paper or to a measurement row we produced.
2. Codings are not findings. Convergence and robustness are our judgements against the rubric; label them that way everywhere.
3. Contradictions stay visible. Where the literature disputes itself, the graph shows the dispute rather than averaging it away.
4. Robustness outranks convergence. A match that dies under rewording is the finding, not a footnote.
5. The design system is settled. Dala, per docs/DESIGN.md. Do not redesign it.
