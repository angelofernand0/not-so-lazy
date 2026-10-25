# Contributing

Start with the [README](README.md), [review stack](docs/PROJECT-STATUS.md) and
[runbook](docs/RUNBOOK.md). Complete source lives on `main`; start new work from the latest main commit.

## Pick a focused change

The next parser priority is split/merge matching, followed by independent label
review and a broader benchmark. Keep parsing, evaluation, scoring and presentation
changes independently reviewable. State the starting commit and open focused
PRs against `main`. The milestone branches are preserved as implementation history.

## Report a reproducible problem

For parser issues, include ticker/CIK, accession, SEC source URL, stage/version,
expected boundary or heading, actual output and a short reproduction. Include
minimal public-source evidence and relevant quality flags. For reading-interface
issues, include route, browser, filters and expected/actual behavior.

Do not include `.env`, personal SEC contact headers, credentials, databases,
private logs or operational caches. Public SEC fixtures need provenance and
checksums. Issue templates cover parser reports and feature requests.

## Preserve evidence and contracts

- Keep historical reports and frozen labels unchanged when measuring fixes.
  Write a new report; document any separately adjudicated label revision.
- Test meaningful boundaries, complete bodies and original offsets. A heading
  being present somewhere is insufficient.
- Update code versions/input signatures when cached outputs change. Rerun
  downstream stages and export JSON. Retain unresolved review flags.
- Preserve original text and half-open Unicode code-point offsets. Frontend
  helpers must convert UTF-16 indexing and validate hashes/span coverage.
- Never add implicit SEC or model downloads to offline commands. Tests block
  real socket connections; fixtures must be self-contained.

## Validate the affected flow

From `pipeline/`:

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy notsolazy
uv run pytest
```

Schema changes need an Alembic migration and upgrade/downgrade checks with
disposable databases. CI also exercises Postgres 17.

From `web/`:

```sh
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
```

Follow `web/AGENTS.md` and installed Next.js guides before frontend code changes.
For data/UI changes, inspect the exported company route and review/error states
in a browser; include screenshots for behavior/layout changes. Documentation-only
edits need command/link/status checks, not a fresh model download or backfill.

PRs should explain the problem, resulting behavior, validation and remaining
limits. Do not claim human-adjudicated accuracy from the development pilot or
economic significance from textual change counts.
