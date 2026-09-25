# CLAUDE.md

Guidance for Claude Code in this repository.

## Project

`legacy-erp-dbt` models the undocumented stock-movement data of a legacy Turkish ERP into
tested marts. Every rule found in the raw data is enforced by an automated dbt test.

The story: a fictional industrial-parts distributor (bearings, seals, belts). It has two
depots, sells to customers and dealers, and buys from suppliers in EUR, USD and TL.

The domain knowledge (traps T1-T16) is in `docs/legacy_erp_dbt_handoff.md`. That file is
local only and git-ignored. Read it for context. Never copy its personal or workspace
details into a committed file.

## Stack

- Python 3.12 in the local `.venv`. Check dbt-core's supported Python versions before
  changing the Python version.
- dbt-core + dbt-duckdb, command line only. DuckDB is one local file with no server.
- pandas + numpy for the synthetic data generator.

## Commands

- The shell is PowerShell on Windows 11. Use relative paths or `C:\...` paths, never `/c/...`.
- Run Python modules with `python -m <module>`, never `python path\to\file.py`.
- Generate the synthetic data: `python -m generator` (writes the CSVs to `seeds\`).
- dbt: `dbt seed`, `dbt build`, `dbt test`, `dbt docs generate`, `dbt docs serve`.

## Workflow

- One design step at a time. Present the step, explain why, give a recommendation, and end
  with a few closed-ended decisions with the default marked.
- Wait for an explicit OK before writing any file or model. Never generate everything at once.
- Propose the design. Do not hand architecture questions back to the user.
- Never create scratch or status files in the repo. Use the session scratchpad.
- Never run `git commit` unless the user asks in that turn. After a change, give a
  ready-to-run `git commit -m "..."` command. No `Co-Authored-By` trailer.
- Do not read files outside this repository unless the user asks. If domain knowledge is
  missing, ask the user.
- Explain why, not just what. Keep sentences short and avoid idioms. The user may write in
  Turkish; answer in English.

## Code style

- English only: names, comments, docstrings, SQL, docs, log messages and commit messages.
- The one exception: raw seed column names keep the ERP's cryptic style (`STHAR_HTUR`,
  `STOK_KODU`). Staging renames them to clear English (`movement_type`, `product_code`).
- `snake_case` for files, models, columns and Python names.
- Python: vectorized pandas (no `iterrows()`), type hints, Google-style docstrings.

## Data rules

- ALL data is synthetic. Invent every company, person, brand, product code, account code
  and price. Never use a real bearing, seal or belt brand name. Never name an employer;
  the README says "a legacy Turkish ERP".
- The generator is deterministic: a fixed seed gives byte-identical CSVs on every run.
- Raw seeds load every column as text. Staging casts the types.
- `trap_manifest` is the generator's answer key. Tests may read it. Models must never read it.

## Scope (v1)

- In: staging, intermediate and mart models, core dbt tests, dbt docs, CI running `dbt build`.
- Out: dashboards or BI, orchestration, incremental models, snapshots.

## dbt conventions

- Staging changes the format, never the meaning: rename, cast, clean, decode single codes.
  One model per raw table, no joins, no aggregations. Business rules live in intermediate.
- Join on the cleaned `product_code`; keep `product_code_raw` for lineage.
- Money and prices are DECIMAL, never DOUBLE. Unknown codes decode to NULL and a
  `not_null` test fails loudly.
- No packages: write custom generic tests in `tests/generic/`. Put test arguments
  under `arguments:`.

## Roadmap

1. Purpose, framing, tooling
2. Synthetic dataset: tables, row counts, planted traps
3. dbt setup: versions, profiles, schemas, seed types
4. Model layers: staging, then intermediate, then marts (one layer at a time)
5. Test suite: each trap mapped to the test that catches it
6. README, dbt docs, CI (GitHub Actions running `dbt build` on every push)
