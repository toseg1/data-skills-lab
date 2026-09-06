# Data Skills Lab

Graded exercises for **SQL (DuckDB)**, **Pandas**, **NumPy** and **APIs**, built on a
fictional asset-management dataset that is generated fresh for every clone.

Companion to the *Data Skills Learning Hub* in Notion: each section here mirrors a
page there, so when an exercise stumps you there is an obvious place to go and read.

## Quickstart

```bash
git clone <this repo> && cd data-skills-lab

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

lab info                         # confirm the wiring
lab generate --seed 1234         # build a dataset (~2s)
```

`lab init`, which draws a seed for you and records it as your session, arrives
with the grading engine. Until then `generate` takes the seed explicitly.

`requirements.txt` pins exact versions and installs the lab itself in editable
mode, so that one command is the whole setup. Versions are pinned deliberately:
grading compares your output against a reference implementation, and pandas
changes behaviour between releases, so a drifting environment can fail an
exercise your code got right.

## How grading works

The grader stores **no expected answers**. It stores a reference implementation,
runs it against the same data your code sees, and compares the two outputs.

```
lab init  ──▶  random seed ──▶  seeded dataset ──▶  data/warehouse.duckdb
                                                          │
                                          ┌───────────────┴───────────────┐
                                    your solve()                  reference solve()
                                          └───────────────┬───────────────┘
                                                     comparator
                                                   pass  or  diff
```

Because the seed is unique to your clone, answers cannot be memorised, shared with
someone else, or worked out by hand — you have to actually run the query. `lab reseed`
draws a new seed when you want to redo a section against fresh numbers.

## The dataset

Northwind Capital, a fictional asset manager. Five **curated** tables — `clients`,
`securities`, `prices`, `trades`, `positions` — plus two **raw** vendor feeds
(`clients_raw`, `trades_raw`) where every column is text and the data is dirty in
the ways real feeds are: duplicated rows, padded strings, mixed date formats.

Curated tables still carry *legitimate* nulls — a client with no onboarding date,
a trade with no commission, a price series with holiday gaps — because handling
those is the work. What they don't carry is corruption; that lives in the raw layer.

Two properties worth knowing, because exercises rely on them:

- **Positions are derived from trades**, so they reconcile exactly. Cumulative
  signed quantity per client and ticker equals the holding on any date.
- **Prices come from a three-factor model** (market, sector, idiosyncratic), so
  same-sector tickers genuinely correlate and a covariance matrix is meaningful.

Roughly 30k price rows, 25k trades and 215k daily position snapshots — about 11 MB,
generated in two seconds, and never committed.

## Layout

```
lab/            the toolkit: CLI, dataset generator, grading engine
exercises/      the files you edit, one directory per section
.corrections/   reference implementations and hints (hidden by convention, not by git)
data/           generated dataset — rebuilt from your seed, never committed
tests/          tests for the toolkit itself, not for your answers
```

## The path

| Track | Sections | Exercises |
| --- | --- | --- |
| Setup | 1 | 3 |
| SQL (DuckDB) | 6 | 70 + 6 capstones |
| Pandas | 5 | 56 + 5 capstones |
| NumPy | 4 | 42 + 4 capstones |
| APIs (yfinance + FastAPI) | 4 | 28 + 1 capstone |

Each section ends with a capstone that combines its functions into something a real
desk would ask for — performance attribution, a NAV series, a minimum-variance
portfolio, an idempotent daily load.

## A note on SQL dialect

Exercises run on **DuckDB**, and every example in the Notion reference has been executed
against DuckDB 1.5. Most of it transfers to Snowflake, Postgres or BigQuery unchanged —
CTEs, window functions, `QUALIFY`, `GROUP BY ALL`, `MERGE`. Where dialects diverge
(`IFF`, `DATEADD`, `TO_CHAR`, `LISTAGG`, `VARIANT`, time travel) the Snowflake appendix
in Notion carries a translation table.

## Status

This is the scaffold. Landing next:

- [x] Repository, tooling and CI
- [x] Seeded synthetic dataset generator
- [ ] Exercise runner CLI and grading engine (`init`, `next`, `check`, `hint`, `solve`, `status`)
- [ ] SQL track
- [ ] Pandas track
- [ ] NumPy track
- [ ] API track

## Development

```bash
ruff check .          # lint
ruff format .         # format
pytest                # test the toolkit
```

CI runs exactly these three on Python 3.12 and 3.13.
