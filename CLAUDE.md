# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`dojinvoice_db` builds and incrementally updates a SQLite database of DLsite doujin voice
(ボイス・ASMR) works.

## Commands

This project uses `uv` for env/deps and `mise` to run tasks (see `mise.toml` for the canonical
task definitions).

```bash
uv sync --all-groups          # install runtime + dev + docs dependency groups
uv run pytest                 # run the full test suite (no network access needed)
uv run pytest tests/test_crawler.py::test_discover_stops_after_known_pages  # single test
uv format                     # run ruff (formatting + lint fixes) — mise task `ruff`
uvx ty check --respect-ignore-files   # type check — mise task `ty`
uv run pymarkdown fix --list-files .  # markdown lint — mise task `pymarkdown`
uv build                      # build sdist/wheel
uv run pdoc dojinvoice_db -o ./docs --docformat google  # generate API docs
mise run tbls                 # regenerate the schema section embedded in README.md
```

`mise run tbls` builds a throwaway schema-only `.tbls.db` from `WorkDatabase`, runs
`tbls doc` into `.tbls-doc/` (config in `.tbls.yml`), and `scripts/embed_tbls_doc.py`
flattens that multi-file output into the `<!-- tbls:start -->` / `<!-- tbls:end -->`
region of `README.md`. Run it after any change to `_SCHEMA` in `db.py`; the `docs`
workflow re-runs it on every push to `master` and commits the result.

Or via mise: `mise run pytest`, `mise run pytest-cov`, `mise run pre-commit` (ruff + ty +
pymarkdown + pyproject-fmt), `mise run ci` (pre-commit + pytest-cov) — this is what CI runs.

The `data` workflow (`.github/workflows/data.yml`) is the production run of this crawler:
monthly at 00:00 JST it restores `dojinvoice.db.zip` from the most recent release that has
it, runs `dvdb crawl --retry-errors` on top, and publishes the result on a
`vX.Y.Z+YYYYMMDD` tag (newest package release tag + JST run date). The crawl is wrapped in
`timeout --signal=INT` so a run that exceeds its window still publishes what it committed,
and `release.yml` skips `+` tags so a snapshot can never republish the package.

The test suite never touches the network: `tests/conftest.py` provides `FakeClient`, a
stand-in for `DlsiteClient` with the same four methods, and `make_info()`, which builds a
plausible ajax entry. Tests that need to exercise the real HTTP layer monkeypatch
`client.api.get` with `FakeGet` in `tests/test_dlsite.py`.

Only one required dependency (`dlsite-async`, which pulls in `aiohttp` + `lxml`). Keep it that
way — everything else (SQLite, argparse, asyncio) is stdlib on purpose.

## Architecture

Five modules, layered as: CLI → crawler (orchestration) → dlsite (network) + db (storage) →
models (plain dataclasses).

- **`dojinvoice_db/models.py`** — dataclasses with no I/O: `SearchQuery` (builds the DLsite
  `fsr` listing URL, including the `key[0]/value` path encoding), `WorkStats` (the
  price/sales/rating figures `dlsite_async.Work` does not model), `CrawlOptions`, `CrawlResult`
  and `parse_file_size`. The canonical work model is `dlsite_async.Work` itself — do not
  duplicate it here.
- **`dojinvoice_db/dlsite.py`** — the network layer, and the reason this project is cheap to
  run. Three request kinds, in increasing cost per work:
  1. `fetch_listing_ids()` — a search listing page, 100 product IDs per request, parsed out of
     `data-list_item_product_id="..."` attributes by regex (`extract_product_ids`) rather than
     an HTML parser, so it does not care about the rest of the markup.
  2. `fetch_product_info()` — `product/info/ajax` accepts a **comma-separated list** of product
     IDs, so one request covers 100 works and returns both the metadata
     `DlsiteAPI.product_info()` returns and the price/sales/rating figures.
  3. `fetch_detail()` — the work page, one request per work; the only source of circle name,
     description, genres and credits. Falls back to the `/announce/` URL for unreleased works.
     It reuses `dlsite_async._scraper.parse_work_html`, a private function, so the import is
     guarded by `_import_parse_work_html()`; if it ever disappears, `fetch_detail` degrades to
     the public `DlsiteAPI.get_work()` (which costs two requests per work instead of one).

  `_Throttle` enforces a minimum interval between requests, a semaphore caps concurrency, and
  `_get_text` retries `_RETRY_STATUSES` with exponential backoff while treating 403/404 as
  "not there" (returns `None`) rather than an error.
- **`dojinvoice_db/db.py`** — the SQLite schema and every query. The schema splits data by
  cost and volatility: `work` (metadata, with `summary_fetched_at`/`detail_fetched_at` marking
  which half was fetched), `work_stat` + `work_stat_history` (figures that keep changing),
  the multi-valued child tables, `fetch_error` and `crawl_state`. `upsert_work(..., detail=)`
  is the single write path: with `detail=False` it only touches the ajax-sourced columns, so a
  cheap refresh can never overwrite expensive detail columns with NULLs. `pending_detail_ids()`
  encodes the "what still needs a work page" rule and `load_work()` rebuilds a
  `dlsite_async.Work` from stored columns so a later run can fetch a detail page without
  re-requesting the ajax info.
- **`dojinvoice_db/crawler.py`** — orchestration over a `CrawlSession` (db + client + options
  + counters + progress callback). Three stages: `discover_ids` → `store_summaries` →
  `fetch_details`, tied together by `crawl()`. Each stage commits as it goes, so `Ctrl-C` never
  loses fetched data and the next run resumes from `detail_fetched_at IS NULL`.
- **`dojinvoice_db/cli.py`** — argparse subcommands (`crawl`, `details`, `refresh`, `show`,
  `stats`), each a thin wrapper that builds a `CrawlSession` and runs it under `asyncio.run`.
  Progress goes to stderr (rewriting one line when it is a TTY), results to stdout.

## The request-economy invariants

These are the point of the project; changes that break them are regressions even if tests pass:

- **The listing stops early.** `discover_ids` walks newest-first and breaks after
  `stop_after_known_pages` consecutive pages with no new IDs. Only `--full` reads to the end.
- **A work page is fetched once.** `detail_fetched_at` is the marker. The only automatic
  re-fetches are (a) works whose release date has passed since their detail was fetched, i.e.
  announcements that have since gone on sale — deliberately *not* every run while they are
  still announced — and (b) an explicit `--detail-stale-days`/`--stale-days` window.
- **Bulk data is fetched in batches.** Anything that can go through `product/info/ajax` should
  go through it 100 IDs at a time, never one work per request.
- **Failures are remembered.** `fetch_error.attempts` reaching `MAX_ERROR_ATTEMPTS` takes a
  work out of the pending set until `--retry-errors`.

## Testing conventions

Tests mirror the module split 1:1: `tests/test_models.py`, `tests/test_dlsite.py`,
`tests/test_db.py`, `tests/test_crawler.py`, `tests/test_cli.py`, with shared fakes in
`tests/conftest.py`. Crawler and CLI tests assert on *which requests were made*
(`client.listing_requests` / `info_requests` / `detail_requests`), not just on stored rows —
that is how the invariants above stay enforced.
