# Ingestion backend

A WebSocket service that pulls papers from bibliographic APIs and streams the
results as they arrive. It is the machine half of roadmap phase 2: **semi-automated
ingestion with a human review gate**.

What it does: search an upstream API for one axis or one query, page through the
results, drop anything already in the corpus, and emit each surviving record as a
candidate — streamed to the client and appended to `data/ingest/`.

What it does not do, by design:

- It never writes `data/sources.json`, `data/axes.json` or `data/protocols.json`.
  Promotion into the corpus is a human act.
- It never asserts a judgement. `domain`, `major`, `cluster` and the axis tags
  arrive as `null` or as proposals under `review`, because those are codings
  against the rubric and not facts an API reported.
- It never invents a number. A citation count is copied with the date it was read
  and the upstream field it came from; a record with no count gets `null`.

Stdlib Python only — no install step, no dependency file.

## Running it

```bash
python3 -m server                                   # ws://127.0.0.1:8787/ws
python3 -m server --port 9000 --contact you@example.org
python3 -m server --token "$(openssl rand -hex 16)" # require a token on connect
```

| Flag | Environment | Default | Meaning |
|---|---|---|---|
| `--host` | `SIMULXALIVE_WS_HOST` | `127.0.0.1` | bind address; loopback on purpose |
| `--port` | `SIMULXALIVE_WS_PORT` | `8787` | bind port |
| `--token` | `SIMULXALIVE_WS_TOKEN` | none | require `?token=…` on the handshake |
| `--allow-origin` | `SIMULXALIVE_WS_ORIGINS` | localhost dev ports | browser origins accepted |
| `--allow-any-origin` | — | off | accept any `Origin` |
| `--contact` | `SIMULXALIVE_CONTACT` | none | address sent upstream for the polite pool |
| `--rate` | — | `5.0` | upstream requests per second |
| `--no-stage` | — | staging on | stream results without writing them |
| — | `SIMULXALIVE_OPENALEX_KEY` | none | OpenAlex api key, if you have one |

A browser page on any site can open a socket to localhost, so an unknown `Origin`
is refused with 403. Clients with no `Origin` header (curl, the CLI below) connect
normally.

There is a client for driving it by hand:

```bash
python3 tools/pull_papers.py --list-axes
python3 tools/pull_papers.py --axis tom-false-belief --side machine \
        --source crossref --limit 20 --from-year 2022
```

## Sources

| Name | Gives | Notes |
|---|---|---|
| `openalex` | metadata, `cited_by_count`, `referenced_works` | the phase-2 source; reference ids are carried on the candidate so lineage edges can be proposed later |
| `crossref` | metadata, `is-referenced-by-count` | DOI-registered records; the fallback when OpenAlex is unavailable or out of budget |

The two citation measures are not the same measure, which is why every count
carries `field` naming which one it is.

## Protocol

JSON text frames, one message per frame, `ws://<host>:<port>/ws`.

A client message is `{"type": …, "id": …, "params": {…}}`. `id` is optional and
is echoed on every direct response to that command. Commands are handled off the
read loop, so a `pull.cancel` is heard while a pull is streaming; responses to
different commands may therefore interleave, and `id` is how you tell them apart.
Every server message has a `type` and a `ts`.

### Commands

| `type` | `params` | Answers with |
|---|---|---|
| `hello` | — | `hello`: version, sources, corpus size, limits |
| `ping` | — | `pong` |
| `sources.list` | — | `sources` |
| `corpus.axes` | `side` | `axes`: every axis with its derived discovery query |
| `pull.start` | see below | `ack`, then the job event stream |
| `pull.cancel` | `job` | `ack`, then `job.cancelled` |
| `jobs.list` | — | `jobs`: this connection's pulls and their counts |

`pull.start` parameters, all optional except that one of `axis` or `query` must
be present:

| Parameter | Default | Meaning |
|---|---|---|
| `source` | `openalex` | which adapter to pull from |
| `axis` | — | axis id from `data/axes.json`; its query is derived from the label and instrument |
| `query` | — | free text, used instead of the derived query |
| `side` | `any` | `human`, `machine`, `bridge` — adds a clause to a derived query |
| `from_year`, `to_year` | — | publication date filter |
| `limit` | 100 | how many records to fetch, capped at 2000 |
| `per_page` | 50 | upstream page size, never above `limit` |
| `include_known` | `false` | also emit records that were skipped as already known |
| `stage` | server default | write the candidates to `data/ingest/` |
| `open_access` | `false` | restrict to open-access records where the source supports it |

An unknown parameter is an error rather than a silent no-op — a typo in a pull is
better loud than half-honoured.

```json
{"type": "pull.start", "id": "a1",
 "params": {"axis": "tom-false-belief", "side": "machine",
            "source": "crossref", "limit": 25, "from_year": 2022}}
```

### Events

| `type` | When | Carries |
|---|---|---|
| `ack` | a command was accepted | `command`, `job` |
| `job.started` | the pull begins | resolved `query`, `params`, `staged_path`, `known_keys` |
| `paper` | a record survived dedup | `seq`, `dedup`, `record` |
| `job.progress` | every 10 records | running counts — **droppable**, see backpressure |
| `job.done` | the pull finished | `summary`, `staged_path` |
| `job.failed` | upstream or server failure | `error`, partial `summary` |
| `job.cancelled` | cancelled by the client or by disconnect | partial `summary` |
| `error` | a command was refused | `error`, echoed `id` |

`dedup` on a `paper` event is one of:

| `status` | Meaning |
|---|---|
| `new` | not seen before; staged |
| `in_corpus` | already in `data/sources.json` (`matched` names it) |
| `already_staged` | pulled by an earlier job and still awaiting review |
| `duplicate_in_run` | the same record came back twice in this pull |

Matching is by DOI, then upstream id, then normalised title (case, punctuation and
accents removed). `reason` says which one hit. Records that are not `new` are
counted but not emitted unless `include_known` is set.

### Failure codes

`bad_request`, `unknown_command`, `unknown_source`, `unknown_axis`, `unknown_job`,
`too_many_jobs`, `upstream_error`, `upstream_rate_limited`, `upstream_unavailable`,
`internal_error`.

`upstream_rate_limited` carries `retry_after` in seconds. The server retries a
short wait itself; a long one — OpenAlex answers an exhausted budget with a wait
measured in hours — fails the job immediately rather than holding the connection.

## Backpressure

Each connection has a bounded outbound queue. `paper` and terminal events wait for
room, which slows the fetch loop to whatever the client can absorb; `job.progress`
is dropped rather than queued, since a stale progress count is worth nothing. A
client that stops reading entirely is dropped when it misses a ping.

Limits: 2 concurrent pulls per connection, 4 per server, 1 MiB per message,
2000 records per pull.

## Staging

```
data/ingest/job_0001.jsonl        one candidate per line
data/ingest/job_0001.meta.json    query, parameters, final counts, state
```

`data/ingest/` is gitignored: these are machine output, not corpus data. A
candidate looks like this:

```json
{
  "kind": "candidate",
  "proposed_id": "grazzani2026",
  "title": "False belief attribution in toddlers: …",
  "authors": ["Ilaria Grazzani", "…"],
  "year": 2026,
  "venue": "Frontiers in Developmental Psychology",
  "doi": "10.3389/fdpys.2026.1727052",
  "citations": {"value": 0, "as_of": "2026-09-14",
                "field": "crossref.is-referenced-by-count"},
  "references": [],
  "review": {"status": "pending", "proposed_axes": ["tom-false-belief"],
             "domain": null, "major": null, "cluster": null},
  "provenance": {"via": "ingest", "source": "crossref",
                 "source_id": "10.3389/fdpys.2026.1727052",
                 "query": {"axes": ["tom-false-belief"], "q": "…"},
                 "job": "job_0001", "fetched_at": "2026-09-14T16:45:13+00:00",
                 "accepted_by": null}
}
```

`proposed_id` is a suggestion in the style of the seed bibliography, not an
identity: a candidate has no id until a person accepts it. `accepted_by` stays
null until the review step (a later phase-2 milestone) fills it in.

## Layout

| Path | What |
|---|---|
| `server/wsframe.py` | RFC 6455 framing, no I/O |
| `server/wsserver.py` | handshake, connection loops, heartbeat |
| `server/protocol.py` | command validation, event construction |
| `server/session.py` | per-connection dispatch and job ownership |
| `server/jobs.py` | the pull loop: fetch, map, dedup, stage, emit |
| `server/sources/` | adapters, the shared HTTP client, the registry |
| `server/corpus.py` | the existing corpus and the dedup index |
| `server/queries.py` | discovery queries derived from the taxonomy |
| `server/records.py` | candidate construction and provenance |
| `server/staging.py` | the `data/ingest/` writer |
| `server/client.py` | small client, used by the CLI and the tests |

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

No network: adapters are tested against sample payloads, and the end-to-end tests
run a real server over a real socket with a fake source behind it.
