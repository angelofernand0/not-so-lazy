# Runbook

## Offline scaffold

From `pipeline/`: `uv sync --locked`, `uv run nsl doctor`, `uv run nsl init-db`,
then `uv run alembic upgrade head`. The initial metadata has no stage tables.
`uv run nsl doctor --require-sec` verifies SEC identity without a network request.

The root `.env` is loaded when commands run from `pipeline/`. Relative database
and data paths are relative to the working directory, so use the documented
working directories consistently. Never commit `.env` or cached documents.

From `web/`: `npm ci`, then `npm run dev`. Production: `npm run build` creates
`web/out/`, which any static file host can serve.

## Required checks

Pipeline: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy notsolazy`, `uv run pytest`.
Frontend: `npm run lint`, `npm run typecheck`, `npm run build`.

## Planned operations

Milestone 2 introduces `universe refresh`, discovery and cached fetching, with
required `SEC_USER_AGENT` contact and a shared <=8 requests/second limiter.
Milestones 3–7 add stage commands and the review queue. Milestone 8 activates
schedules and publishing. Do not schedule placeholder stages.

For a bad filing, the future workflow will retain raw HTML, record review
flags, rerun only affected stage versions, and republish after verification.
Do not delete raw evidence to work around a parser issue.

Adding a section will use the same pipeline with item-specific boundary and
segmentation configuration. No additional sections are part of the MVP.
